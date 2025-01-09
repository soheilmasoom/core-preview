from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.authentication import CustomTokenAuthentication
from accounts.models import User
from accounts.permissions import IsBasicVerified
from financial.fast_payment.getter import get_fast_payment_client
from financial.fast_payment.vandar_client import logger
from financial.models.fast_payment_bank import FastPaymentBank
from financial.models.fast_payment_gateway import FastPaymentGateway


class BanksSerializer(serializers.ModelSerializer):
    class Meta:
        model = FastPaymentBank
        fields = (
            'id', 'code', 'name', 'is_healthy_on_direct_debit',
            'max_withdrawal_amount', 'max_withdrawal_amount_per_transaction',
            'withdrawal_amount_currency', 'max_withdrawal_daily_count',
            'max_mandate_validity_duration', 'mandate_validity_duration_unit',
            'payer_authentication_type'
        )



class BanksView(APIView):
    serializer_class = BanksSerializer

    def get(self, request, *args, **kwargs):
        gateway = FastPaymentGateway.live_objects.first()

        if not gateway:
            raise ValidationError('امکان دریافت لیست بانک ها وجود ندارد.')

        banks = FastPaymentBank.live_objects.filter(gateway=gateway)

        serializer = BanksSerializer(banks, many=True)

        return Response(serializer.data)


class AuthorizationIdView(APIView):
    # authentication_classes = permission_classes = ()

    def get(self, request, *args, **kwargs):
        user = self.request.user
        bank_id = request.GET.get('bank_id')

        gateway = FastPaymentGateway.live_objects.first()

        if not gateway:
            raise ValidationError('امکان ایجاد مجوز وجود ندارد.')

        if not bank_id:
            raise ValidationError({'bank_id': 'فیلد شناسه بانک نیاز است.'})

        # if user.level <= User.LEVEL1:
        #     raise ValidationError({'user': 'ابتدا احراز هویت کنید.'})

        try:
            bank = FastPaymentBank.objects.get(id=bank_id)
            client = get_fast_payment_client(gateway)
            url = client.get_authorization_create_url(user, bank)

            return Response({'url': url},)

        except FastPaymentBank.DoesNotExist:
            raise ValidationError('شناسه بانک نامعتبر است.')




