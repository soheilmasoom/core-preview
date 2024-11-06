import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.authentication import TokenAuthentication, get_authorization_header, BaseAuthentication
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import AccessToken
import jwt
from decouple import config

from accounts.models import CustomToken, SystemConfig
from accounts.utils.ip import get_client_ip

logger = logging.getLogger(__name__)

CUSTOM_JWT_SECRET_KEY = config('CUSTOM_JWT_SECRET_KEY')


class TradeClosedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Trade closed.')
    default_code = 'trade_error'


class CustomTokenAuthentication(TokenAuthentication):
    model = CustomToken

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        print('here ', self.keyword.lower().encode())
        print(auth)
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None
        # activate('en-US')
        print(auth)
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
            print('try in auth cred 1', key)
            token = model.objects.select_related('user').get(
                # Q(ip_list__contains=[request_ip]) | Q(ip_list__isnull=True) | Q(ip_list=[]),
                key=key
            )
            print('try in auth cred 2')
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

        if validated_token.get('type'):
            raise InvalidToken("Token does not have the privilege for this request.")
        return validated_token

    def authenticate(self, request):
        validated_token = self.get_valid_token(request)
        if not validated_token:
            return None

        return self.get_user(validated_token), validated_token

    def get_valid_token(self, request):
        header = self.get_header(request)
        if header is None:
            return None
        print("the header: ", header)
        raw_token = self.get_raw_token(self.get_header(request))
        print("the raw token: ", raw_token)
        if raw_token is None:
            return None

        return self.get_validated_token(raw_token)


class WidgetJWTAuthentication(CustomJWTAuthentication):
    token_type = 'widget'

    def get_validated_token(self, raw_token):
        validated_token = JWTAuthentication().get_validated_token(raw_token)

        return validated_token

    def authenticate(self, request):
        validated_token = super().get_valid_token(request)
        if not validated_token:
            return None

        if 'type' not in validated_token:
            raise InvalidToken("Token missing 'type' field")

        if validated_token.get('type') != self.token_type:
            msg = _(f'Token type must be "{self.token_type}"')
            raise exceptions.AuthenticationFailed(msg)

        return self.get_user(validated_token), validated_token


class InitTelegramJWTAuthentication(JWTAuthentication):
    token_type = 'init_telegram'

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, CUSTOM_JWT_SECRET_KEY, algorithms=["HS256"])
            # payload = super().get_validated_token(token)
            print("This is payload:  ", payload)
            user_id = payload.get("user_id")
            # try:
            #     print("we arrrrrrrrrrre here")
            #     # user = User.objects.get(id='1')
            #     # print(user)
            # except User.DoesNotExist:
            #     raise AuthenticationFailed("User not found")

            user = self.get_user(payload)
            token = TelegramAccessToken.for_user(user)

            token['allowed_apis'] = ['api/v1/telegram/user-info']
            print(token)
            print(token['allowed_apis'])
            return user, token

        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token")

class TelegramJWTAuthentication(CustomJWTAuthentication):
    token_type = 'telegram'

    def get_validated_token(self, raw_token):
        validated_token = JWTAuthentication().get_validated_token(raw_token)
        print(")))))))))))))) ", validated_token.get('type'))
        print(validated_token)
        return validated_token

    def authenticate(self, request):
        print(request)
        validated_token = super().get_valid_token(request)
        print(validated_token)
        if not validated_token:
            return None

        if 'type' not in validated_token:
            raise InvalidToken("Token missing 'type' field")
        validated_token['allowed_apis'] = ['telegram_get_user_info', 'bookmark_assets']
        print("Allowed APIs in validated_token:", validated_token.get('allowed_apis'))
        if validated_token.get('type') != self.token_type:
            msg = _(f'Token type must be "{self.token_type}"')
            raise exceptions.AuthenticationFailed(msg)
        return self.get_user(validated_token), validated_token

    def get_raw_token(self, header):
        if header is None:
            return None

        header_str = header.decode("utf-8")

        if header_str.startswith("telegram "):
            return header_str.split(" ")[1]
        # elif header_str.startswith("Bearer "):
        #     return header_str.split(" ")[1]

        return None


class TelegramAccessToken(AccessToken):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['type'] = 'telegram'


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
