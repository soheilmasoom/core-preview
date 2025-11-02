from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, Account, RefreshToken as RefreshTokenModel, Referral
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.validators import mobile_number_validator
from accounts.utils.login import set_login_activity
from accounts.utils.signup import create_traffic_source, set_missions_to_user


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
    promotion = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    referral_code = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)

    @staticmethod
    def validate_referral_code(code):
        if code and not Referral.objects.filter(code=code).exists():
            raise ValidationError('کد معرف نامعتبر است.')
        return code


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    account, _ = Account.objects.get_or_create(user=user)
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
        promotion = serializer.validated_data.get('promotion', '')
        utm = serializer.validated_data.get('utm') or {}
        referral_code = serializer.validated_data.get('referral_code')

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

            # Handle promotion and traffic source for existing users (if not set)
            if promotion and not user.mission_journey:
                set_missions_to_user(user, promotion)

            # Create traffic source if not exists
            if not hasattr(user, 'traffic_source'):
                create_traffic_source(request, user, utm)

            # Handle referral code for existing users (if not already referred)
            if referral_code:
                account = user.get_account()
                if not account.referred_by:
                    account.referred_by = Referral.objects.get(code=referral_code)
                    account.save(update_fields=['referred_by'])

                    from gamify.utils import check_prize_achievements, Task
                    check_prize_achievements(account.referred_by.owner, Task.REFERRAL)

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
            # New user flow - return verification token with metadata
            # Store promotion, utm, and referral_code in the context for signup
            return Response({
                'is_registered': False,
                'token': str(otp_code.token),
                'scope': VerificationCode.SCOPE_PHONE_LOGIN,
                'promotion': promotion,
                'utm': utm,
                'referral_code': referral_code
            })