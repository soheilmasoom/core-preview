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
from accounts.authentication import CustomJWTAuthentication, WidgetAccessToken

from accounts.models import User, Company, TrafficSource, Referral
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.utils.ip import get_client_ip
from accounts.utils.login import set_login_activity
from accounts.validators import mobile_number_validator, national_card_code_validator, password_validator, company_national_id_validator
from analytics.utils.yandex import send_yandex_event
from gamify.models import MissionJourney
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from datetime import timedelta

from ledger.widget.widget import Widget

logger = logging.getLogger(__name__)


class InitiateSignupWidgetSerializer(serializers.Serializer):
    source = serializers.CharField(required=False, write_only=True)
    phone = serializers.CharField(required=True, validators=[mobile_number_validator], trim_whitespace=True)


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

        if request.user.is_authenticated:
            return Response({'msg': 'already logged in', 'code': 1})

        serializer = InitiateSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        VerificationCode.send_otp_code(phone, self.scope)
        print("what", self.scope)
        return Response({'msg': 'otp sent', 'code': 0})


class InitiateSignupWidgetView(InitiateSignupView):
    scope = VerificationCode.SCOPE_VERIFY_PHONE_WIDGET


class WidgetSignupSerializer(serializers.Serializer):
    token = serializers.UUIDField(write_only=True, required=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    national_code = serializers.CharField(allow_null=True, allow_blank=True, write_only=True, required=False,
                                                validators=[national_card_code_validator])

    def create(self, validated_data):
        token = validated_data.pop('token')
        otp_code = VerificationCode.get_by_token(token, VerificationCode.SCOPE_VERIFY_PHONE_WIDGET)
        if not otp_code:
            raise ValidationError({'token': 'توکن نامعتبر است.'})
        phone = otp_code.phone
        user_status = Widget.get_user_verification_status(phone)
        if not validated_data.get('national_code') and user_status == Widget.NEW_USER:
            raise ValidationError({'national_code': 'وارد کردن کد ملی الزامی است.'})

        if user_status == Widget.VERIFIED_USER:
            if User.objects.filter(phone=phone).exists():
                return User.objects.get(phone=phone)
            else:
                raise ValidationError({'user': 'کاربر پیدا نشد.'})

        elif user_status == Widget.UNVERIFIED_USER:
            if validated_data.get('national_code'):
                if User.objects.filter(phone=phone).exists():
                    user = User.objects.get(phone=phone)
                    user.national_code = validated_data.get('national_code')
                    user.save(update_fields=['national_code'])
                    return user
                else:
                    raise ValidationError({'user': 'کاربر پیدا نشد.'})
            else:
                raise ValidationError({'national_code': 'وارد کردن کد ملی الزامی است.'})

        elif user_status == Widget.NEW_USER:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=phone,
                    phone=phone,
                )
                if validated_data.get('national_code'):
                    user.national_code = validated_data.get('national_code')
                if config('SHOW_NINJA_TO_ALL', cast=bool, default=False):
                    user.show_community = True

                user.set_password(None)
                user.save()

            signup_serializer = SignupSerializer()
            signup_serializer.create_traffic_source(user, validated_data.get('utm') or {})
            signup_serializer.set_missions_to_user(user)

            return user


class SignupSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
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
        promotion = validated_data.get('promotion')
        if promotion not in User.PROMOTIONS:
            promotion = MissionJourney.get_default_promotion() or ''

        with transaction.atomic():

            user = User.objects.create_user(
                username=phone,
                phone=phone,
                promotion=promotion
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

        self.create_traffic_source(user, utm)

        self.set_missions_to_user(user)

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


class SignupWidgetView(CreateAPIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = [BurstRateThrottle, ]
    serializer_class = WidgetSignupSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        access_token = WidgetAccessToken.for_user(user)
        access_token.set_exp(lifetime=timedelta(minutes=30))
        token = {'access': str(access_token)}

        return Response(token, status=201)
