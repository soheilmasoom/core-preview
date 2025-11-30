from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView, UpdateAPIView
from rest_framework.response import Response
from accounts.throttle import SustainedRateThrottle, BurstRateThrottle
from rest_framework.views import APIView

from accounts.models import VerificationCode, User
from accounts.validators import telephone_number_validator


class InitiateTelephoneSerializer(serializers.Serializer):
    telephone = serializers.CharField(required=True, validators=[telephone_number_validator], trim_whitespace=True)


class InitiateTelephoneVerifyView(APIView):
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        serializer = InitiateTelephoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telephone = serializer.validated_data['telephone']

        user = request.user

        if user.telephone_verified:
            raise ValidationError('شماره تلفن تایید شده است.')

        VerificationCode.send_otp_code(telephone, VerificationCode.SCOPE_TELEPHONE, user=user)

        return Response({'msg': 'otp sent', 'code': 0})


class TelephoneOTPVerifySerializer(serializers.ModelSerializer):
    code = serializers.CharField(write_only=True, required=True)

    def update(self, user, validated_data):
        code = validated_data.get('code')
        telephone = validated_data.get('telephone')

        otp_code = VerificationCode.get_by_code(code, telephone, VerificationCode.SCOPE_TELEPHONE, user=user)

        if not otp_code:
            raise ValidationError({'code': 'کد نامعتبر است.'})

        otp_code.set_code_used()

        user.telephone_verified = True
        user.telephone = telephone
        user.save(update_fields=['telephone_verified', 'telephone'])

        return user

    class Meta:
        model = User
        fields = ('code', 'telephone', 'telephone_verified')
        read_only_fields = ('telephone_verified', )

        extra_kwargs = {
            'telephone': {'required': True},
        }


class TelephoneOTPVerifyView(UpdateAPIView):
    serializer_class = TelephoneOTPVerifySerializer

    def get_object(self):
        return self.request.user
