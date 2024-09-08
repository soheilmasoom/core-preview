import logging

from rest_framework import serializers
from rest_framework.generics import CreateAPIView
from django.contrib.auth import login
from django.core.exceptions import ValidationError

from accounts.throttle import SustainedRateThrottle, BurstRateThrottle
from accounts.validators import password_validator
from django.contrib.auth.password_validation import validate_password
from accounts.authentication import SetPasswordJWTAuthentication
from accounts.utils.login import set_login_activity

logger = logging.getLogger(__name__)


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, write_only=True, validators=[password_validator])

    def create(self, validated_data):
        request = self.context['request']
        user = request.user

        password = validated_data.pop('password')

        validate_password(password=password, user=user)

        user.set_password(password)
        user.save(update_fields=['password'])
        login(request, user)
        try:
            set_login_activity(
                request=request,
                user=user,
                is_sign_up=True,
            )
        except ValueError:
            logger.exception('Error in setting login activity for signup')

        return user


class SetPasswordView(CreateAPIView):
    authentication_classes = (SetPasswordJWTAuthentication,)
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    serializer_class = SetPasswordSerializer
