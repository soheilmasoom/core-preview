from datetime import timedelta

from django.contrib.auth import login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import VerificationCode


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    otp_code = serializers.CharField(write_only=True)
    totp = serializers.CharField(allow_null=True, allow_blank=True, required=False)

    def validate(self, data):
        user = self.context['request'].user
        code = data.get('otp_code')
        password = data.get('password')
        old_pass = data.get('old_password')
        otp_code = VerificationCode.get_by_code(code, user.phone, VerificationCode.SCOPE_CHANGE_PASSWORD, user)
        totp = data.get('totp', None)
        if not otp_code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})

        if not user.check_password(old_pass):
            raise ValidationError({'old_password': 'رمز عبور قبلی بدرستی وارد نشده است'})

        if not user.is_2fa_valid(totp):
            raise ValidationError({'totp': 'شناسه ‌دوعاملی صحیح نمی‌باشد.'})
        otp_code.set_code_used()
        validate_password(password=password, user=user)

        return data

    def update(self, user, validated_data):
        user.set_password(validated_data['password'])
        user.suspend(timedelta(days=1), 'تغییر رمز عبور')
        user.save(update_fields=['password'])
        request = self.context['request']
        login(request, user)

        return user


class ChangePasswordView(APIView):
    def patch(self, request):
        user = self.request.user

        change_password_serializer = ChangePasswordSerializer(
            instance=user,
            data=request.data,
            partial=True,
            context={
                'request': request
            }
        )
        change_password_serializer.is_valid(raise_exception=True)

        change_password_serializer.save()
        return Response({'msg': 'password update successfully'})
