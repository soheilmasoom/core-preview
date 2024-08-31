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
from .signup_view import SignupSerializer, InitiateSignupView
from ledger.widget.widget import Widget

logger = logging.getLogger(__name__)


class InitiateSignupWidgetSerializer(serializers.Serializer):
    source = serializers.CharField(required=False, write_only=True)
    phone = serializers.CharField(required=True, validators=[mobile_number_validator], trim_whitespace=True)


class InitiateSignupWidgetView(InitiateSignupView):
    scope = VerificationCode.SCOPE_VERIFY_PHONE_WIDGET


class WidgetSignupSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, required=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    national_code = serializers.CharField(allow_null=True, allow_blank=True, write_only=True, required=False,
                                                validators=[national_card_code_validator])

    def create(self, validated_data):
        token = validated_data.pop('token')
        print("what-token", token)
        otp_code = VerificationCode.get_by_token(token, VerificationCode.SCOPE_VERIFY_PHONE_WIDGET)
        print("what-token", otp_code)

        if not otp_code:
            raise ValidationError({'token': 'توکن معتبر نیست.'})
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

class SignupWidgetView(CreateAPIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = [BurstRateThrottle, ]
    serializer_class = WidgetSignupSerializer

    def create(self, request, *args, **kwargs):
        print("SignupWidgetView")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        access_token = WidgetAccessToken.for_user(user)
        access_token.set_exp(lifetime=timedelta(minutes=30))
        token = {'access': str(access_token)}

        return Response(token, status=201)
