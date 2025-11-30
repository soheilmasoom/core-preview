from rest_framework import serializers

from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.validators import email_validator
from rest_framework.views import APIView
from rest_framework.generics import UpdateAPIView
from accounts.models import User, VerificationCode
from rest_framework.exceptions import ValidationError
from accounts.models import EmailVerificationCode
from rest_framework.response import Response


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, validators=[email_validator], trim_whitespace=True)


class EmailVerifyView(APIView):
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        user = self.request.user

        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        if User.objects.filter(email=email).exists():
            raise ValidationError('ایمیل وارد شده در سیستم وجود دارد.')

        EmailVerificationCode.send_otp_code(email, EmailVerificationCode.SCOPE_VERIFY_EMAIL, user)

        return Response({'msg': 'otp send', 'code': 0})


class EmailOTPVerifySerializer(serializers.ModelSerializer):

    code = serializers.CharField(write_only=True, required=True)
    sms_code = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('code', 'email', 'sms_code',)
        read_only_fields = ('email', )

    def update(self, user, validated_data):
        code = validated_data.get('code')
        sms_code = validated_data.get('sms_code')

        code = EmailVerificationCode.get_by_code(code, user, EmailVerificationCode.SCOPE_VERIFY_EMAIL)
        sms_code = VerificationCode.get_by_code(sms_code, user.phone, VerificationCode.SCOPE_VERIFY_EMAIL)

        if not code:
            raise ValidationError({'code': 'کد ایمیل نامعتبر است'})

        if not sms_code:
            raise ValidationError({'code': 'کد موبایل نامعتبر است'})

        code.set_code_used()
        sms_code.set_code_used()

        user.email = code.email.lower()
        user.save(update_fields=['email'])

        from gamify.utils import check_prize_achievements, Task
        check_prize_achievements(user.get_account(), Task.SET_EMAIL)

        return user


class EmailOTPVerifyView(UpdateAPIView):
    serializer_class = EmailOTPVerifySerializer
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def get_object(self):
        return self.request.user
