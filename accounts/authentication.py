import logging

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import CustomToken, SystemConfig
from accounts.utils.ip import get_client_ip

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)


class TradeClosedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Trade closed.')
    default_code = 'trade_error'


class CustomTokenAuthentication(TokenAuthentication):
    model = CustomToken

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None
        # activate('en-US')

        if len(auth) == 1:
            msg = _('Invalid token header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid token header. Token string should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeError:
            msg = _('Invalid token header. Token string should not contain invalid characters.')
            raise exceptions.AuthenticationFailed(msg)

        return self.authenticate_credentials(token, request)

    def authenticate_credentials(self, key, request):
        model = self.get_model()
        request_ip = get_client_ip(request=request)
        logger.info('request ip for %s is %s, x-forward %s, remote addr %s' % (
            request.path, request_ip, request.META.get('HTTP_X_FORWARDED_FOR'), request.META.get('REMOTE_ADDR')))

        try:
            token = model.objects.select_related('user').get(
                # Q(ip_list__contains=[request_ip]) | Q(ip_list__isnull=True) | Q(ip_list=[]),
                key=key
            )

        except model.DoesNotExist:
            logger.info(f'requested ip: {request_ip}')
            raise exceptions.AuthenticationFailed(_('Invalid token.'))

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed(_('User inactive or deleted.'))

        return (token.user, token)


class WithdrawTokenAuthentication(CustomTokenAuthentication):
    def authenticate(self, request):
        auth_detail = super().authenticate(request)
        if not auth_detail:
            return None
        user, token = auth_detail
        if CustomToken.WITHDRAW not in token.scopes:
            msg = _('permission denied')
            raise exceptions.AuthenticationFailed(msg)
        return user, token


class TradeTokenAuthentication(CustomTokenAuthentication):
    def authenticate(self, request):
        auth_detail = super().authenticate(request)
        if not auth_detail:
            return None
        user, token = auth_detail
        if CustomToken.TRADE not in token.scopes:
            msg = _('permission denied')
            raise exceptions.AuthenticationFailed(msg)

        if request.method == 'POST':
            if SystemConfig.get_system_config().disable_trade_with_api and not user.get_account().is_system():
                msg = _('trade is closed')
                raise TradeClosedException(msg)

        return user, token


class CustomJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        validated_token = super().get_validated_token(raw_token)

        if validated_token.get('type') == 'widget':
            raise InvalidToken("Token does not have the privilege for this request.")

        return validated_token

    def authenticate(self, request):
        validated_token = self.get_valid_token(self, request)
        if not validated_token:
            return None

        return self.get_user(validated_token), validated_token

    def get_valid_token(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(self.get_header(request))
        if raw_token is None:
            return None

        return self.get_validated_token(raw_token)


class WidgetJWTAuthentication(CustomJWTAuthentication):
    def get_validated_token(self, raw_token):
        validated_token = JWTAuthentication().get_validated_token(raw_token)

        return validated_token

    def authenticate(self, request):
        validated_token = super().get_valid_token(request)
        if not validated_token:
            return None

        if 'type' not in validated_token:
            raise InvalidToken("Token missing 'type' field")

        if validated_token.get('type') != 'widget':
            msg = _('Token type must be "widget"')
            raise exceptions.AuthenticationFailed(msg)

        return self.get_user(validated_token), validated_token


class WidgetAccessToken(AccessToken):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['type'] = 'widget'


class SetPasswordJWTAuthentication(CustomJWTAuthentication):
    def get_validated_token(self, raw_token):
        validated_token = JWTAuthentication().get_validated_token(raw_token)

        return validated_token

    def authenticate(self, request):
        validated_token = super().get_valid_token(request)
        if not validated_token:
            return None

        if 'type' not in validated_token:
            raise InvalidToken("Token missing 'type' field")

        if validated_token.get('type') != 'setpass':
            msg = _('Token type must be "setpass"')
            raise exceptions.AuthenticationFailed(msg)

        return self.get_user(validated_token), validated_token


class SetPasswordAccessToken(AccessToken):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['type'] = 'setpass'


def is_app(request):
    return isinstance(request.successful_authenticator, CustomJWTAuthentication)
