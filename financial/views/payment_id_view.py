from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from financial.models import PaymentId, PaymentIdGateway, BankAccount
from financial.utils.bank import get_bank_from_slug
from financial.utils.payment_id_client import get_payment_id_client


class PaymentIdGatewaySerializer(serializers.ModelSerializer):
    bank = serializers.SerializerMethodField()

    def get_bank(self, general_bank: PaymentIdGateway):
        bank = get_bank_from_slug(general_bank.bank)
        return bank.as_dict()

    class Meta:
        model = PaymentIdGateway
        fields = ('iban', 'name', 'bank', 'deposit_address')


class PaymentIdSerializer(serializers.ModelSerializer):
    pay_id = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()

    def create(self, validated_data):
        user = self.context['request'].user

        if user.level <= User.LEVEL1:
            raise ValidationError({'user': 'ابتدا احراز هویت کنید.'})

        if not BankAccount.objects.filter(user=user, verified=True, deleted=False):
            raise ValidationError({'iban': 'شما باید حداقل یک حساب بانکی تایید شده داشته باشید.'})

        gateway = PaymentIdGateway.live_objects.filter(type=PaymentIdGateway.JIBIT_OLD).first()

        client = get_payment_id_client(gateway)

        return client.create_payment_id(user)

    def get_pay_id(self, payment_id: PaymentId):
        if not payment_id.verified:
            return ''
        else:
            return payment_id.pay_id

    def get_destination(self, payment_id: PaymentId):
        return PaymentIdGatewaySerializer(payment_id.gateway).data

    class Meta:
        model = PaymentId
        read_only_fields = fields = ('pay_id', 'verified', 'destination')


class PaymentIdViewsSet(ModelViewSet):
    serializer_class = PaymentIdSerializer

    def get_object(self):
        gateway = PaymentIdGateway.live_objects.filter(type=PaymentIdGateway.JIBIT_OLD).first()
        return get_object_or_404(PaymentId, user=self.request.user, gateway=gateway, deleted=False)
