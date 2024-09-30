import logging

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import ChangePhone
from accounts.models import User
from accounts.models import VerificationCode
from accounts.validators import mobile_number_validator
from ledger.utils.fields import PENDING

from multimedia.fields import ImageField

logger = logging.getLogger(__name__)


class InitiateChangePhoneSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True)
    totp = serializers.CharField(required=False, allow_null=True, allow_blank=True, write_only=True)

    def validate(self, data):
        user = self.context['request'].user
        otp = data.get('otp')
        password = data.get('password')
        totp = data.get('totp', None)

        validate_password(password=password, user=user)

        otp_verification = VerificationCode.get_by_code(
            code=otp,
            phone=user.phone,
            scope=VerificationCode.SCOPE_CHANGE_PHONE_INIT,
            user=user
        )

        if not otp_verification:
            raise ValidationError('کد ارسال شده نامعتبر است.')

        if not user.is_2fa_valid(totp):
            raise ValidationError({'totp': 'شناسه‌ دوعاملی صحیح نمی‌باشد.'})

        if ChangePhone.objects.filter(status=PENDING, user=user):
            raise ValidationError(
                'شما در حال حاضر درخواست تایید نشده‌ای دارید. لطفا تا تایید یا رد درخواست‌تان منتظر بمانید.'
            )

        otp_verification.set_code_used()
        data['token'] = otp_verification.token

        return data


class InitiateChangePhone(APIView):
    def post(self, request):
        serializer = InitiateChangePhoneSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response({'token': serializer.validated_data['token']})


class UserVerifySerializer(serializers.Serializer):
    new_phone = serializers.CharField(write_only=True, validators=[mobile_number_validator], trim_whitespace=True)
    token = serializers.CharField(write_only=True)

    def validate(self, data):
        new_phone = data.get('new_phone')
        token = data.get('token')
        token_verification = VerificationCode.get_by_token(token, VerificationCode.SCOPE_CHANGE_PHONE_INIT)
        if not token_verification:
            raise ValidationError('توکن نامعتبر است.')

        token_verification.set_token_used()
        VerificationCode.send_otp_code(self.context['request'], new_phone, VerificationCode.SCOPE_NEW_PHONE)
        return data


class NewPhoneVerifySerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    selfie_image = ImageField(write_only=True)

    def validate(self, data):
        token = data.pop('token')
        user = self.context['request'].user

        token_verification = VerificationCode.get_by_token(token, VerificationCode.SCOPE_NEW_PHONE)
        if not token_verification:
            raise ValidationError('توکن نامعتبر است.')

        if ChangePhone.any_active_for(user):
            raise ValidationError({'user': 'شما در حال حاضر درخواست فعالی دارید.'})

        new_phone = token_verification.phone
        if User.objects.filter(phone=new_phone):
            raise ValidationError(
                'شما با این شماره موبایل قبلا ثبت نام کرده‌اید. لطفا خارج شوید و با این شماره موبایل دوباره وارد شوید.'
            )

        if ChangePhone.objects.filter(new_phone=new_phone, status=PENDING).exclude(user=user):
            raise ValidationError(
                'امکان تغییر به این شماره موبایل در حال حاضر وجود ندارد.'
            )

        data['new_phone'] = new_phone

        return data

    def save(self, **kwargs):
        user = self.context['request'].user

        return ChangePhone.objects.create(
            user=user,
            **self.validated_data
        )


class ChangePhoneView(APIView):
    def post(self, request):
        serializer = UserVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'msg': 'کد باموفقیت ارسال شد.'})

    def put(self, request):
        serializer = NewPhoneVerifySerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({'msg': 'درخواست تغییر شماره موبایل با موفقیت ثبت شد.'}, status=200)
