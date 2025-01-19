from rest_framework.generics import ListAPIView
from rest_framework import serializers

from financial.models import PaymentIdGateway
from financial.utils.bank import get_bank_from_slug


class PaymentGatewaySerializer(serializers.ModelSerializer):
    bank = serializers.SerializerMethodField()

    def get_bank(self, general_bank: PaymentIdGateway):
        bank = get_bank_from_slug(general_bank.bank)
        if bank:
            return bank.as_dict()

    class Meta:
        model = PaymentIdGateway
        fields = ('id', 'type', 'name', 'bank', 'iban', 'deposit_address', 'card_pan')


class PaymentGatewaysView(ListAPIView):
    serializer_class = PaymentGatewaySerializer

    def get_queryset(self):
        return PaymentIdGateway.live_objects.all()
