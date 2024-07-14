from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView

from accounts.models import User
from accounts.throttle import SustainedRateThrottle, BurstRateThrottle
from accounts.models.phone_verification import VerificationCode
from django.conf import settings


class VerifyOTPSerializer(serializers.ModelSerializer):

    def create(self, validated_data):
        phone = validated_data['phone']
        code = validated_data['code']
        scope = validated_data['scope']

        if scope in VerificationCode.RESTRICTED_VERIFY_SCOPES:
            raise ValidationError({'scope': f'restricted {scope}'})

        otp_code = VerificationCode.get_by_code(
            code=code,
            phone=phone,
            scope=scope
        )

        if not otp_code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})

        otp_code.set_code_used()

        if scope == VerificationCode.SCOPE_VERIFY_PHONE and User.objects.filter(phone=phone).exists():
            raise ValidationError({'scope': 'شما با این شماره موبایل قبلا ثبت نام کرده‌اید. لطفا از قسمت ورود، وارد شوید.'})

        if scope == VerificationCode.SCOPE_FORGET_PASSWORD and not otp_code.user:
            raise ValidationError({
                'scope': 'شما حساب کاربری فعالی ندارید. برای استفاده از {} لطفا ثبت‌نام کنید.'.format(settings.BRAND)
            })

        return otp_code

    class Meta:
        model = VerificationCode
        fields = ('code', 'phone', 'token', 'scope')
        read_only_fields = ('token', )
        extra_kwargs = {
            'code': {'required': True, 'write_only': True},
            'phone': {'write_only': True},
        }


class VerifyOTPView(CreateAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = VerifyOTPSerializer
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]


class OTPSerializer(serializers.ModelSerializer):

    new_phone = serializers.CharField(required=False)

    def create(self, validated_data):
        scope = validated_data['scope']
        user = validated_data['user']

        if scope in VerificationCode.RESTRICTED_SEND_SCOPES:
            raise ValidationError({'scope': f'restricted {scope}'})

        if scope == VerificationCode.SCOPE_TELEPHONE:
            phone = user.telephone

        elif scope == VerificationCode.SCOPE_CHANGE_PHONE:
            if 'new_phone' in validated_data:
                phone = validated_data['new_phone']
            else:
                raise ValidationError('شماره همراه وارد نشده است.')

        else:
            phone = user.phone

        if not phone:
            raise ValidationError('امکان ارسال کد وجود ندارد.')

        VerificationCode.send_otp_code(phone=phone, scope=scope, user=user)

        return {}

    @property
    def data(self):
        return {
            'msg': 'sent'
        }

    class Meta:
        model = VerificationCode
        fields = ('scope', 'new_phone')


class SendOTPView(CreateAPIView):
    serializer_class = OTPSerializer
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
