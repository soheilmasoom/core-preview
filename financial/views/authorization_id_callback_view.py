from django.http import JsonResponse
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from financial.fast_payment.getter import get_fast_payment_client
from financial.models.authorization_id import AuthorizationId
from financial.models.fast_payment_bank import FastPaymentBank
from financial.models.fast_payment_gateway import FastPaymentGateway


class AuthorizationIdCallbackView(APIView):
    def get(self, request, *args, **kwargs):
        token = request.GET.get('token')
        authorization_id = request.GET.get('authorization_id')
        status = request.GET.get('status')
        error_code = request.GET.get('error_code')

        if status == "SUCCEED" and token and authorization_id:
            try:
                auth_id = AuthorizationId.objects.get(token=token)
            except AuthorizationId.DoesNotExist:
                raise ValidationError(f'شناسه مجوز یافت نشد.')

            if auth_id.verified:
                raise ValidationError(f'مجوز برای این شناسه قبلا تایید شده است.')

            auth_id.verified = True
            auth_id.auth_id = authorization_id
            auth_id.save(update_fields=['verified', 'auth_id'])

        elif status == "FAILED":
            raise ValidationError(f' تایید مجوز ناموفق: {error_code}')

        elif status == "FAILED_TO_ACCESS_BANK":
            raise ValidationError('امکان تایید مجوز وجود ندارد.')

        return JsonResponse({'message': 'مجوز با موفقیت تایید شد.'}, status=200)
