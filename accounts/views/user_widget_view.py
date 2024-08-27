from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from accounts.models import User
from accounts.throttle import SustainedRateThrottle, BurstRateThrottle
from accounts.models.phone_verification import VerificationCode
from django.conf import settings
from rest_framework.response import Response


class UserWidgetView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        token = request.data["token"]
        otp_code = VerificationCode.get_by_token(token, VerificationCode.SCOPE_VERIFY_PHONE_WIDGET)

        if not otp_code:
            raise ValidationError({'token': 'توکن نامعتبر است.'})

        status = User.get_user_verification_status(otp_code.phone)
        return Response({"status": status})

