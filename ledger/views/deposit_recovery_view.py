import re

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.serializers import ModelSerializer

from ledger.models import DepositRecoveryRequest, Network, Asset
from multimedia.fields import ImageField


class DepositRecoverySerializer(ModelSerializer):
    coin = serializers.CharField(required=True, write_only=True)
    network = serializers.CharField(required=True, write_only=True)
    image = ImageField(write_only=True)

    class Meta:
        model = DepositRecoveryRequest
        fields = ('id', 'coin', 'network', 'memo', 'amount', 'trx_hash', 'receiver_address', 'description', 'image')
        extra_kwargs = {
            'memo': {'required': False},
            'description': {'required': False}
        }

    def validate(self, attrs):
        network_symbol = attrs.pop('network', None)
        coin = attrs.pop('coin', None)

        network = Network.objects.filter(symbol=network_symbol).first()
        asset = Asset.objects.filter(symbol=coin).first()

        if network and network.address_regex and not re.match(network.address_regex, attrs['receiver_address']):
            raise ValidationError('آدرس به فرمت درستی وارد نشده است.')

        comment = ''

        if not asset:
            comment += f'Asset: {coin}\n'

        if not network:
            comment += f'Network: {network_symbol}\n'

        return {
            **attrs,
            'network': network,
            'asset': asset,
            'comment': comment,
        }


class DepositRecoveryView(CreateAPIView):
    serializer_class = DepositRecoverySerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
