from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import CreateAPIView
from rest_framework.serializers import ModelSerializer

from django.core.exceptions import ValidationError
from django_otp.plugins.otp_totp.models import TOTPDevice, default_key

from datetime import timedelta

from accounts.utils.validation import get_jalali_now
from multimedia.fields import ImageField
from accounts.models import Forget2FA, EmailNotification
from accounts.throttle import SustainedRateThrottle, BurstRateThrottle
from accounts.models.phone_verification import VerificationCode

ACTIVATE = 'activate'
DEACTIVATE = 'deactivate'


class TOTPSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    sms_code = serializers.CharField(write_only=True)

    def validate(self, data):
        user = self.context['request'].user
        token = data.get('token')
        sms_code = data.get('sms_code')
        sms_verification_code = VerificationCode.get_by_code(sms_code, user.phone, VerificationCode.SCOPE_2FA, user)
        if not sms_verification_code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})
        device = TOTPDevice.objects.filter(user=user).first()
        if device is None:
            raise ValidationError({'device': 'ابتدا بارکد را دریافت کنید.'})
        if not device.verify_token(token):
            raise ValidationError({'token': 'شناسه ‌دوعاملی صحیح نمی‌باشد.'})
        sms_verification_code.set_code_used()
        return data


class TOTPView(APIView):

    def post(self, request):
        user = request.user
        device = TOTPDevice.objects.filter(user=user).first()
        scope = request.data.get('scope', ACTIVATE if device is None or device.confirmed is False else DEACTIVATE)
        VerificationCode.send_otp_code(
            request=request,
            phone=user.phone,
            scope=VerificationCode.SCOPE_2FA,
            user=user
        )

        response_data = {}

        if scope == ACTIVATE:
            if device is None:
                device = TOTPDevice.objects.create(user=user, confirmed=False, name='main')
            if device.confirmed is False:
                device.key = default_key()
                device.save(update_fields=['key'])
                response_data['config'] = device.config_url

        return Response(response_data)

    def put(self, request):
        user = request.user
        totp_verify_serializer = TOTPSerializer(
            data=request.data,
            context={
                'request': request
            }
        )
        totp_verify_serializer.is_valid(raise_exception=True)
        device = TOTPDevice.objects.filter(user=user).first()
        if not device.confirmed:
            device.confirmed = True
            device.save(update_fields=['confirmed'])

            EmailNotification.send_by_template(
                recipient=user,
                template='2fa_activation',
                check_spam=True,
                context={
                    'now': get_jalali_now(),
                }
            )

            return Response({'msg': 'ورود دومرحله‌ای باموفقیت برای حساب کاربری فعال شد.'})
        else:
            return Response({'msg': 'ورود دو مرحله‌ای فعال می باشد.'})

    def delete(self, request):
        user = request.user
        totp_de_active_serializer = TOTPSerializer(
            data=request.data,
            context={
                'request': request
            }
        )
        totp_de_active_serializer.is_valid(raise_exception=True)
        device = TOTPDevice.objects.filter(user=user).first()

        if device.confirmed:
            device.confirmed = False
            device.save(update_fields=['confirmed'])

            EmailNotification.send_by_template(
                recipient=user,
                template='2fa_deactivation',
                check_spam=True,
                context={
                    'now': get_jalali_now(),
                }
            )

            user.suspend(duration=timedelta(days=1), reason='غیرفعال کردن شناسه ‌دوعاملی')
            return Response({'msg': 'ورود دومرحله‌ای باموفقیت برای حساب کاربری غیرفعال شد.'})
        else:
            return Response({'msg': 'ورود دومرحله‌ای غیرفعال است.'})


class Forget2FAInitSerializer(serializers.Serializer):
    login = serializers.CharField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        login = attrs['login'].lower()
        password = attrs['password']
        user = authenticate(login=login, password=password)

        if not user:
            raise ValidationError({'user': 'نام کاربری یا رمز عبور نادرست است.'})

        if not user.is_2fa_active():
            raise ValidationError({'totp': 'شناسه دوعاملی غیرفعال می‌باشد.'})

        attrs['user'] = user

        return attrs

    def create(self, validated_data):
        user = self.validated_data['user']
        VerificationCode.send_otp_code(
            request=self.context['request'],
            phone=user.phone,
            scope=VerificationCode.SCOPE_FORGET_2FA,
            user=user
        )


class Forget2FAInitView(CreateAPIView):
    serializer_class = Forget2FAInitSerializer
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return Response({'msg': 'user is already authenticated'})

        return self.create(request, *args, **kwargs)


class Forget2FASerializer(ModelSerializer):
    token = serializers.CharField(write_only=True)
    selfie_image = ImageField(write_only=True)

    def validate(self, attrs):
        token = attrs.pop('token')
        verification_code = VerificationCode.get_by_token(token=token, scope=VerificationCode.SCOPE_FORGET_2FA)

        if not verification_code:
            raise ValidationError({'token': 'توکن نامعتبر است.'})

        if Forget2FA.any_active_for(verification_code.user):
            raise ValidationError({'user': 'شما در حال حاضر درخواست فعالی دارید.'})

        attrs['user'] = verification_code.user
        return attrs

    class Meta:
        model = Forget2FA
        fields = ('token', 'selfie_image',)


class Forget2FAView(CreateAPIView):
    serializer_class = Forget2FASerializer
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    class Meta:
        model = Forget2FA
