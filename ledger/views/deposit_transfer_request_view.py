import logging
from decimal import Decimal

from django.contrib.auth.mixins import UserPassesTestMixin
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView, get_object_or_404

from accounts.authentication import CustomTokenAuthentication
from accounts.utils.admin import url_to_edit_object
from accounts.utils.telegram import send_system_message
from ledger.models import Network, Asset, DepositAddress, AddressKey, NetworkAsset
from ledger.models.transfer import Transfer
from ledger.requester.architecture_requester import get_network_architecture
from ledger.utils.fields import PENDING, DONE, CANCELED, INIT
from ledger.utils.fraud import verify_crypto_deposit
from ledger.utils.price import get_last_price

logger = logging.getLogger(__name__)


class DepositSerializer(serializers.ModelSerializer):
    network = serializers.CharField(max_length=16, write_only=True)
    sender_address = serializers.CharField(max_length=256, write_only=True)
    receiver_address = serializers.CharField(max_length=256, write_only=True)
    coin = serializers.CharField(max_length=8, write_only=True)
    memo = serializers.CharField(max_length=256, write_only=True, allow_blank=True, allow_null=True)

    class Meta:
        model = Transfer
        fields = ['status', 'amount', 'trx_hash', 'network', 'sender_address', 'receiver_address', 'coin', 'memo']

    def create(self, validated_data):
        network_symbol = validated_data.get('network')
        sender_address = validated_data.get('sender_address')
        receiver_address = validated_data.get('receiver_address')
        network = Network.objects.get(symbol=network_symbol)
        memo = validated_data.get('memo') or ''

        need_memo = network.need_memo

        if (need_memo and not memo) or (not need_memo and memo):
            raise ValidationError({'memo': 'null memo for memo networks error'})

        deposit_address = DepositAddress.objects.filter(
            network=network,
            address=receiver_address,
            address_key__memo=memo
        ).first()

        if deposit_address and deposit_address.address_key.deleted:
            raise ValidationError({'receiver_address': 'old deposit address not supported'})

        if not deposit_address:
            address_key = get_object_or_404(
                AddressKey,
                address=receiver_address,
                architecture=get_network_architecture(network),
                deleted=False,
                memo=memo
            )

            deposit_address, _ = DepositAddress.objects.get_or_create(
                address=receiver_address,
                network=network,
                defaults={
                    'address_key': address_key
                }
            )

        coin = validated_data.get('coin')

        asset = Asset.objects.filter(symbol=coin).first()
        coin_mult = 1

        if not asset and coin:
            asset = Asset.objects.filter(original_symbol=coin).first()

            if asset:
                coin_mult = asset.get_coin_multiplier()

        if not asset:
            logger.warning('invalid coin for deposit', extra={'coin': coin})
            raise ValidationError({'coin': 'invalid coin'})

        wallet = asset.get_wallet(deposit_address.address_key.account)

        network_asset = get_object_or_404(NetworkAsset, asset=asset, network=network)

        if not network_asset.can_deposit_enabled():
            raise ValidationError({'deposit_enable': 'false'})

        status = validated_data.get('status')

        if status not in (PENDING, DONE, CANCELED):
            raise ValidationError({'status': 'invalid status %s' % status})

        transfer = Transfer.objects.filter(
            network=network,
            trx_hash=validated_data.get('trx_hash'),
            deposit=True
        ).order_by('-created').first()

        valid_transitions = [
            (PENDING, DONE),
            (PENDING, CANCELED),
        ]

        if transfer:
            if transfer.status == status:
                return transfer

            if (transfer.status, status) not in valid_transitions:
                raise ValidationError({
                    'status': 'invalid status transition (%s -> %s)' % (transfer.status, status)
                })

        else:
            amount = Decimal(validated_data.get('amount')) / coin_mult

            min_deposit = network_asset.get_min_deposit()
            if min_deposit and amount < min_deposit:
                raise ValidationError({
                    'type': 'ignore',
                    'reason': 'small amount'
                })

            price_usdt = get_last_price(asset.symbol + Asset.USDT)
            price_irt = get_last_price(asset.symbol + Asset.IRT)

            transfer, _ = Transfer.objects.get_or_create(
                deposit=True,
                trx_hash=validated_data.get('trx_hash'),
                network=network,
                wallet=wallet,
                deposit_address=deposit_address,
                out_address=sender_address,
                defaults={
                    'amount': amount,
                    'usdt_value': amount * price_usdt,
                    'irt_value': amount * price_irt,
                    'memo': memo
                }
            )

        if not verify_crypto_deposit(transfer):
            status = INIT
            send_system_message("Verify deposit: %s" % transfer, link=url_to_edit_object(transfer))

        transfer.change_status(status)

        return transfer


class DepositTransferUpdateView(CreateAPIView, UserPassesTestMixin):
    authentication_classes = [CustomTokenAuthentication]
    serializer_class = DepositSerializer

    def test_func(self):
        permission_check = self.request.user.has_perm('ledger.add_transfer') and\
                           self.request.user.has_perm('ledger.change_transfer')
        return permission_check
