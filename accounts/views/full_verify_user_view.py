from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from accounts.tasks.verify_user import alert_user_verify_status, verify_user_national_code
from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.utils.telegram import send_support_message
from multimedia.fields import ImageField


class FullVerificationSerializer(serializers.ModelSerializer):
    selfie_image = ImageField()

    def update(self, user, validated_data):
        if user and user.verify_status in (User.PENDING, User.VERIFIED):
            raise ValidationError('امکان تغییر اطلاعات وجود ندارد.')

        if user.level >= User.LEVEL3:
            raise ValidationError('کاربر تایید شده است.')

        if user.level == User.LEVEL1:
            raise ValidationError('امکان احراز هویت سطح ۳ کاربر وجود ندارد.')

        if user.selfie_image_verified and user.national_code_phone_verified:
            user.change_status(User.VERIFIED)
            return user

        if not user.selfie_image_verified:
            user.selfie_image = validated_data['selfie_image']
            user.selfie_image_verified = None
            user.save(update_fields=['selfie_image', 'selfie_image_verified'])

        link = url_to_edit_object(user)
        send_support_message(
            message='لطفا کاربر را برای احراز هویت کامل بررسی کنید.',
            link=link
        )

        if user.national_code_phone_verified is None:
            verify_user_national_code.delay(user.id)

        user.change_status(User.PENDING)

        return user

    class Meta:
        fields = (
            'verify_status', 'level', 'selfie_image', 'selfie_image_verified', 'national_code_verified'
        )
        model = User
        read_only_fields = (
            'verify_status', 'level', 'selfie_image_verified', 'national_code_verified'
        )
        extra_kwargs = {
            'selfie_image': {'required': True},
        }


class FullVerificationViewSet(ModelViewSet):
    serializer_class = FullVerificationSerializer

    def get_object(self):
        return self.request.user
