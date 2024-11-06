import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import CustomToken, SystemConfig
from accounts.utils.ip import get_client_ip

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
    token_type = None

    def authenticate(self, request):
        auth = super(CustomJWTAuthentication, self).authenticate(request)
        if not auth:
            return

        user, validated_token = auth

        if not validated_token:
            return

        if validated_token.get('type') != self.token_type:
            return

        return user, validated_token


class WidgetJWTAuthentication(CustomJWTAuthentication):
    token_type = 'widget'


class WidgetAccessToken(AccessToken):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['type'] = 'widget'


class SetPasswordJWTAuthentication(WidgetJWTAuthentication):
    token_type = 'setpass'


class SetPasswordAccessToken(AccessToken):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['type'] = 'setpass'


def is_app(request):
    return isinstance(request.successful_authenticator, CustomJWTAuthentication)
