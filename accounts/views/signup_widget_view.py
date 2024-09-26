import logging
from datetime import timedelta

from decouple import config
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from django.conf import settings

from accounts.authentication import WidgetAccessToken
from accounts.models import User
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle
from accounts.validators import mobile_number_validator, national_card_code_validator
from ledger.widget.widget import Widget
from .signup_view import SignupSerializer, InitiateSignupView
from ..utils.signup import create_traffic_source, set_missions_to_user

logger = logging.getLogger(__name__)


class InitiateSignupWidgetView(InitiateSignupView):
    scope = VerificationCode.SCOPE_VERIFY_PHONE_WIDGET


class WidgetSignupSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, required=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    national_code = serializers.CharField(allow_null=True, allow_blank=True, write_only=True, required=False,
                                                validators=[national_card_code_validator])

    def create(self, validated_data):
        token = validated_data.pop('token')
        otp_code = VerificationCode.get_by_token(token, VerificationCode.SCOPE_VERIFY_PHONE_WIDGET)

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
                    national_code = validated_data.get('national_code')
                    if User.objects.filter(national_code=national_code, national_code_verified=True).exists():
                        raise ValidationError({"national_code": f'شما قبلا با موبایل دیگری در {settings.BRAND} ثبت نام کرده اید، لطفا از آن شماره استفاده کنید.'})
                    user.national_code = national_code
                    user.save(update_fields=['national_code'])
                    return user
                else:
                    raise ValidationError({'user': 'کاربر پیدا نشد.'})
            else:
                raise ValidationError({'national_code': 'وارد کردن کد ملی الزامی است.'})

        elif user_status == Widget.NEW_USER:
            national_code = validated_data.get('national_code')
            if User.objects.filter(national_code=national_code, national_code_verified=True).exists():
                raise ValidationError({"national_code": f'شما قبلا با موبایل دیگری در {settings.BRAND} ثبت نام کرده اید، لطفا از آن شماره استفاده کنید.'})

            with transaction.atomic():
                user = User.objects.create_user(
                    username=phone,
                    phone=phone,
                )
                if national_code:
                    user.national_code = national_code
                if config('SHOW_NINJA_TO_ALL', cast=bool, default=False):
                    user.show_community = True

                user.set_unusable_password()
                user.save()

            utm = validated_data.get('utm') or {}
            create_traffic_source(self.context['request'], user, utm)
            set_missions_to_user(user)

            return user


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
