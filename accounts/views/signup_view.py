import logging

from decouple import config, Csv
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, Company, Referral
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.utils.login import set_login_activity
from accounts.utils.signup import create_traffic_source, set_missions_to_user
from accounts.validators import mobile_number_validator, password_validator, company_national_id_validator
from analytics.utils.yandex import send_yandex_event

logger = logging.getLogger(__name__)


class InitiateSignupSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, validators=[mobile_number_validator], trim_whitespace=True)


class InitiateSignupView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    scope = VerificationCode.SCOPE_VERIFY_PHONE

    def post(self, request):
        if settings.DEBUG_OR_TESTING_OR_STAGING:
            req_origin = request.META.get('HTTP_ORIGIN')
            print('HTTP_ORIGIN: {}'.format(req_origin))
            if req_origin in config('SIGNUP_CLOSED_DOMAINS', cast=Csv(), default=''):
                raise ValidationError('امکان ثبت‌نام وجود ندارد.')

        if request.user.is_authenticated and self.scope == VerificationCode.SCOPE_VERIFY_PHONE:
            return Response({'msg': 'already logged in', 'code': 1})

        serializer = InitiateSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        VerificationCode.send_otp_code(request, phone, self.scope)
        return Response({'msg': 'otp sent', 'code': 0})


class SignupSerializer(serializers.Serializer):
    token = serializers.UUIDField(write_only=True, required=True)
    password = serializers.CharField(required=True, write_only=True, validators=[password_validator])
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    referral_code = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    promotion = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    source = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    company_national_id = serializers.CharField(allow_null=True, allow_blank=True, write_only=True,
                                                required=False, validators=[company_national_id_validator])

    @staticmethod
    def validate_referral_code(code):
        if code and not Referral.objects.filter(code=code).exists():
            raise ValidationError(_('Referral code is invalid'))
        return code

    def create(self, validated_data):
        token = validated_data.pop('token')
        otp_code = VerificationCode.get_by_token(token, VerificationCode.SCOPE_VERIFY_PHONE)
        password = validated_data.pop('password')
        company_national_id = validated_data.get('company_national_id') or None

        if not otp_code:
            raise ValidationError({'token': 'توکن نامعتبر است.'})

        if (User.objects.filter(phone=otp_code.phone).exists() or
                (company_national_id and Company.objects.filter(national_id=company_national_id).exists())):
            raise ValidationError({'phone': 'شما قبلا در سیستم ثبت‌نام کرده‌اید. لطفا از قسمت ورود، وارد شوید.'})

        validate_password(password=password)

        phone = otp_code.phone
        promotion = validated_data.get('promotion', '')

        with transaction.atomic():
            user = User.objects.create_user(
                username=phone,
                phone=phone,
            )

            if company_national_id:
                Company.objects.create(national_id=company_national_id, user=user)

            if config('SHOW_NINJA_TO_ALL', cast=bool, default=False):
                user.show_community = True

            user.set_password(password)
            user.save()

            if validated_data.get('referral_code'):
                account = user.get_account()
                account.referred_by = Referral.objects.get(code=validated_data['referral_code'])
                account.save()

                from gamify.utils import check_prize_achievements, Task
                check_prize_achievements(account.referred_by.owner, Task.REFERRAL)

            # otp_code.set_token_used()

        utm = validated_data.get('utm') or {}

        request = self.context['request']
        create_traffic_source(request, user, utm)
        set_missions_to_user(user, promotion)

        send_yandex_event(user, 'sign_up', {'id': user.id})

        return user


class SignupView(CreateAPIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    serializer_class = SignupSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        login(self.request, user)
        try:
            set_login_activity(
                request=self.request,
                user=user,
                is_sign_up=True,
            )
        except ValueError:
            logger.exception('Error in setting login activity for signup')
