import re

from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.serializers import ModelSerializer

from ledger.models.asset import CoinField
from ledger.models.network import NetworkField
from ledger.models import DepositRecoveryRequest
from multimedia.fields import ImageField


class DepositRecoverySerializer(ModelSerializer):
    coin = CoinField(source='asset', required=True)
    network = NetworkField(required=True)
    image = ImageField(write_only=True)

    class Meta:
        model = DepositRecoveryRequest
        fields = ('id', 'coin', 'network', 'memo', 'amount', 'trx_hash', 'receiver_address', 'description', 'image')
        extra_kwargs = {
            'memo': {'required': False},
            'description': {'required': False}
        }

    def validate(self, attrs):
        if not re.match(attrs['network'].address_regex, attrs['receiver_address']):
            raise ValidationError('آدرس به فرمت درستی وارد نشده است.')
        return attrs


class DepositRecoveryView(CreateAPIView):
    serializer_class = DepositRecoverySerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
