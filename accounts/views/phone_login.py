from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, Account, RefreshToken as RefreshTokenModel
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.validators import mobile_number_validator
from accounts.utils.login import set_login_activity


class PhoneLoginInitSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, validators=[mobile_number_validator])


class PhoneLoginInitView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        if request.user.is_authenticated:
            return Response({'msg': 'already logged in', 'code': 1})

        serializer = PhoneLoginInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']

        try:
            VerificationCode.send_otp_code(
                request=request,
                phone=phone,
                scope=VerificationCode.SCOPE_PHONE_LOGIN
            )
        except ValidationError as e:
            return Response({
                'msg': str(e),
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'msg': 'otp sent',
            'code': 0
        })


class PhoneLoginVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, validators=[mobile_number_validator])
    code = serializers.CharField(required=True)
    client_info = serializers.JSONField(required=False)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    account, _ = Account.objects.get_or_create(user=user)  # FIXED: Added underscore
    refresh['account_id'] = account.id

    refresh_token_model, _ = RefreshTokenModel.objects.get_or_create(token=str(refresh))
    refresh['refresh_id'] = refresh_token_model.id

    refresh_token_model.token = str(refresh)
    refresh_token_model.save(update_fields=['token'])

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class PhoneLoginVerifyView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        serializer = PhoneLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']
        client_info = serializer.validated_data.get('client_info')

        otp_code = VerificationCode.get_by_code(
            code=code,
            phone=phone,
            scope=VerificationCode.SCOPE_PHONE_LOGIN
        )

        if not otp_code:
            return Response({
                'msg': 'کد پیامک نامعتبر است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(phone=phone).first()

        if user:
            # Existing user flow - return JWT tokens
            otp_code.set_code_used()

            tokens = get_tokens_for_user(user)

            login_activity = set_login_activity(
                request=request,
                user=user,
                client_info=client_info,
                refresh_token=tokens['refresh']
            )

            return Response({
                **tokens,
                'is_registered': True,
                'user': {'id': user.id}
            })
        else:
            # New user flow - return verification token
            return Response({
                'is_registered': False,
                'token': str(otp_code.token),
                'scope': VerificationCode.SCOPE_PHONE_LOGIN
            })