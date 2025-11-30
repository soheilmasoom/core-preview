import logging
from datetime import timedelta

from decouple import config
from rest_framework import serializers
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer, \
    TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenViewBase

from accounts.authentication import CustomJWTAuthentication, CustomTokenAuthentication
from accounts.models import Account, LoginActivity, RefreshToken as RefreshTokenModel
from accounts.models import User
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.utils.login import set_login_activity

logger = logging.getLogger(__name__)


class JWTTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])

        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }


class JWTTokenRefreshView(TokenViewBase):
    serializer_class = JWTTokenRefreshSerializer


def user_has_delegate_permission(user):
    return str(user.id) in config('DELEGATION_PERMITTED_USERS', '').split(',')


class DelegatedAccountMixin:
    @staticmethod
    def get_account_variant(request):
        if request.auth and request.user and user_has_delegate_permission(request.user) and \
                getattr(request.auth, 'token_type', None) == 'access' and \
                hasattr(request.auth, 'payload') and request.auth.payload.get('account_id'):
            # activate('en-US')

            return Account.objects.get(id=request.auth.payload.get('account_id')), request.auth.payload.get('variant')

        if request.user:
            return request.user.get_account(), None
        return None, None


class InternalTokenObtainPairSerializer(serializers.Serializer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mask'] = serializers.IntegerField(required=True)
        self.fields['variant'] = serializers.CharField(required=True, allow_null=True)

    @classmethod
    def get_token(cls, user, mask=None, variant=None):
        token = RefreshToken.for_user(user)

        account = Account.objects.get(user_id=user.pk)
        if mask and user_has_delegate_permission(user):
            token['account_id'] = mask
            token['variant'] = variant
        else:
            token['account_id'] = account.id

        return token

    def validate(self, attrs):
        mask = attrs.pop('mask', None)
        variant = attrs.pop('variant', None)
        data = super().validate(attrs)

        refresh = self.get_token(self.context['user'], mask, variant)

        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)

        return data


class InternalTokenObtainPairView(TokenObtainPairView):
    authentication_classes = (CustomTokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = InternalTokenObtainPairSerializer

    def get_serializer_context(self):
        return {
            **super(InternalTokenObtainPairView, self).get_serializer_context(),
            'user': self.request.user
        }


class ClientInfoSerializer(serializers.Serializer):
    version = serializers.CharField(required=False, allow_blank=True)

    system_name = serializers.CharField(required=False, allow_blank=True)
    system_version = serializers.CharField(required=False, allow_blank=True)

    unique_id = serializers.CharField(required=False, allow_blank=True)

    brand = serializers.CharField(required=False, allow_blank=True)

    build_id = serializers.CharField(required=False, allow_blank=True)
    build_number = serializers.CharField(required=False, allow_blank=True)

    device = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField(required=False, allow_blank=True)
    device_name = serializers.CharField(required=False, allow_blank=True)
    device_token = serializers.CharField(required=False, allow_blank=True)
    device_type = serializers.CharField(required=False, allow_blank=True)

    display = serializers.CharField(required=False, allow_blank=True)
    mac_address = serializers.CharField(required=False, allow_blank=True)

    manufacturer = serializers.CharField(required=False, allow_blank=True)
    model = serializers.CharField(required=False, allow_blank=True)
    product = serializers.CharField(required=False, allow_blank=True)

    is_table = serializers.BooleanField(required=False)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    totp = serializers.CharField(write_only=True, allow_null=True, allow_blank=True, required=False)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        account = Account.objects.get(user_id=user.pk)
        token['account_id'] = account.id

        refresh_token_model, _ = RefreshTokenModel.objects.get_or_create(token=str(token))

        token['refresh_id'] = refresh_token_model.id

        refresh_token_model.token = str(token)
        refresh_token_model.save(update_fields=['token'])

        return token


class SessionTokenObtainPairSerializer(CustomTokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super(TokenObtainSerializer, self).__init__(*args, **kwargs)

    def validate(self, attrs):
        refresh = self.get_token(self.context['user'])
        data = {'access': str(refresh.access_token)}
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            client_info_serializer = ClientInfoSerializer(data=request.data.get('client_info'))

            client_info = None

            if client_info_serializer.is_valid():
                client_info = client_info_serializer.validated_data
            user = serializer.user
            totp = serializer.initial_data.get('totp')
            # todo: send unsuccessful login message
            if not user.is_2fa_valid(totp):
                return Response({'msg': 'totp required', 'code': -2}, status=status.HTTP_401_UNAUTHORIZED)

            login_activity = set_login_activity(
                request,
                user=serializer.user,
                client_info=client_info,
                refresh_token=serializer.validated_data['refresh']
            )

            if (not login_activity.is_sign_up and
                    LoginActivity.objects.filter(user=user, device=login_activity.device).count() == 1):

                user.suspend(timedelta(hours=1), 'ورود از دستگاه جدید')
            if LoginActivity.objects.filter(user=user, browser=login_activity.browser, os=login_activity.os,
                                            ip=login_activity.ip).count() == 1:
                LoginActivity.send_successful_login_message(login_activity)
            return Response(serializer.validated_data, status=status.HTTP_200_OK)

        except AuthenticationFailed as e:
            recipient = User.objects.filter(phone=serializer.initial_data.get('phone')).first()
            if recipient:
                LoginActivity.send_unsuccessful_login_message(recipient)
            if e is TokenError:
                return Response({'error': e.args[0]}, status=401)
            else:
                raise e


class SessionTokenObtainPairView(TokenObtainPairView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = SessionTokenObtainPairSerializer

    def get_serializer_context(self):
        return {
            **super(SessionTokenObtainPairView, self).get_serializer_context(),
            'user': self.request.user
        }


class TokenLogoutView(APIView):
    authentication_classes = (CustomJWTAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            login_activity = LoginActivity.objects.filter(refresh_token__token=refresh_token).first()

            if login_activity:
                login_activity.destroy()
            else:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response(status=status.HTTP_205_RESET_CONTENT)
        except TokenError as e:
            if str(e) == 'Token is blacklisted':
                return Response(status=status.HTTP_205_RESET_CONTENT)
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
