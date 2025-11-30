from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import VerificationCode
from accounts.models import User
from accounts.validators import mobile_number_validator


class ChangePhoneSerializer(serializers.ModelSerializer):
    new_phone = serializers.CharField(required=True, validators=[mobile_number_validator], trim_whitespace=True)
    code = serializers.CharField(write_only=True, required=True)

    def validate(self, data):

        return data

    def update(self, instance, validated_data):
        user = self.instance
        new_phone = validated_data['new_phone']
        code = validated_data['code']
        code = VerificationCode.get_by_code(code, new_phone, VerificationCode.SCOPE_CHANGE_PHONE, user)

        if user.national_code_verified:
            raise ValidationError('کد ملی شما تایید شده است. امکان تغییر شماره موبایل وجود ندارد.')

        if not code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})

        if User.objects.filter(phone=new_phone):
            raise ValidationError('شما با این شماره موبایل قبلا ثبت نام کرده‌اید. لطفا خارج شوید و با این شماره موبایل دوباره وارد شوید.')

        instance.phone = new_phone
        instance.username = new_phone
        instance.save()

        code.set_code_used()

        return instance

    class Meta:
        model = User
        fields = ('new_phone', 'code',)


class ChangePhoneBeforeVerifyView(APIView):

    def patch(self, request):

        user = self.request.user
        change_phone = ChangePhoneSerializer(
            instance=user,
            data=request.data,
            partial=True
        )

        change_phone.is_valid(raise_exception=True)
        change_phone.save()

        if user.verify_status != User.PENDING and user.level == User.LEVEL1:
            from accounts.tasks import basic_verify_user

            user.national_code_verified = None
            user.change_status(User.PENDING)
            basic_verify_user.delay(user.id)

        return Response({'msg': 'phone change successfully'})
