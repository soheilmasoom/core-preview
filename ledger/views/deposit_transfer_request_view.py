import logging
from decimal import Decimal

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView, get_object_or_404

from accounts.admin_guard.html_tags import url_to_admin_list
from accounts.authentication import CustomTokenAuthentication
from accounts.utils.telegram import send_system_message
from ledger.models import Network, Asset, DepositAddress, AddressKey, NetworkAsset, DepositRecoveryRequest, ProxyWallet
from ledger.models.transfer import Transfer
from ledger.utils.blocklink import get_blocklink_requester
from ledger.utils.fields import PENDING, DONE, CANCELED, INIT
from ledger.utils.fraud import verify_crypto_deposit
from ledger.utils.price import get_last_price
from ledger.utils.str import truncate_str

logger = logging.getLogger(__name__)


class DepositSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField()
    network = serializers.CharField(max_length=16, write_only=True)
    sender_address = serializers.CharField(max_length=256, write_only=True)
    receiver_address = serializers.CharField(max_length=256, write_only=True)
    coin = serializers.CharField(max_length=8, write_only=True)
    memo = serializers.CharField(max_length=256, write_only=True, allow_blank=True, allow_null=True)

    class Meta:
        model = Transfer
        fields = ['status', 'amount', 'trx_hash', 'network', 'sender_address', 'receiver_address', 'coin', 'memo', 'id',
                  'block_number', 'last_block_number']

    def create(self, validated_data):
        receiver_address = validated_data['receiver_address']
        if ProxyWallet.objects.filter(address__iexact=receiver_address).exists():
            raise ValidationError({
                'receiver_address': 'Ignored due to proxy wallet'
            })

        network_symbol = validated_data.get('network')
        sender_address = validated_data['sender_address']
        network = Network.objects.get(symbol=network_symbol)
        memo = validated_data.get('memo') or ''
        status = validated_data.get('status')
        trx_hash = validated_data.get('trx_hash')
        block_number = validated_data.get('block_number')
        last_block_number = validated_data.get('last_block_number')
        coin = validated_data['coin']

        asset = Asset.objects.filter(symbol=coin).first()
        coin_mult = 1

        if not asset:
            asset = Asset.objects.filter(original_symbol=coin).first()

            if not asset:
                raise ValidationError({'coin': 'Ignored due to invalid coin'})

            coin_mult = asset.get_coin_multiplier()

        need_memo = network.deposit_need_memo

        if need_memo and not memo:
            DepositRecoveryRequest.objects.get_or_create(
                blocklink_id=validated_data['id'],
                defaults={
                    'asset': asset,
                    'network': network,
                    'memo': truncate_str(memo, 64),
                    'trx_hash': trx_hash,
                    'amount': Decimal(validated_data.get('amount')) / coin_mult,
                    'receiver_address': receiver_address,
                    'scope': DepositRecoveryRequest.SYSTEM,
                }
            )
            raise ValidationError({'memo': 'Ignored due to empty memo'})

        if not need_memo:
            memo = ''

        q = Q(deleted=False) | Q(accept_deposits=True)

        if need_memo:
            q &= Q(memo=memo)

        arch = get_blocklink_requester().get_network_arch(network)

        if arch == 'ETH':
            q &= Q(address__iexact=receiver_address)
        else:
            q &= Q(address__exact=receiver_address)

        address_keys = list(AddressKey.objects.filter(
            q,
            architecture=arch,
        ))

        if not address_keys:
            raise ValidationError({'receiver_address': 'Ignored due to invalid receiver_address or memo'})

        if len(address_keys) > 1:
            raise ValidationError({'receiver_address': 'Ignored due to multiple address_key matched!'})

        address_key = address_keys[0]

        deposit_address, _ = DepositAddress.objects.get_or_create(
            address_key=address_key,
            network=network,
            defaults={
                'address': address_key.public_address
            }
        )

        wallet = asset.get_wallet(deposit_address.address_key.account)

        network_asset = get_object_or_404(NetworkAsset, asset=asset, network=network)

        if not network_asset.can_deposit_enabled(check_provider=False):
            raise ValidationError({'deposit_enable': 'false'})

        if status not in (PENDING, DONE, CANCELED):
            raise ValidationError({'status': 'invalid status %s' % status})

        transfer = Transfer.objects.filter(
            network=network,
            trx_hash=trx_hash,
            deposit=True,
            deposit_address=deposit_address
        ).order_by('-created').first()

        valid_transitions = [
            (PENDING, DONE),
            (PENDING, CANCELED),
        ]

        if transfer:
            if transfer.status == status:
                transfer.block_number = block_number
                transfer.last_block_number = last_block_number
                transfer.save(update_fields=['last_block_number', 'block_number'])
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
                    'memo': memo,
                    'block_number': block_number,
                    'last_block_number': last_block_number,
                }
            )

        if not network_asset.can_deposit_enabled():
            status = INIT
            transfer.add_comment('init reason: deposit is not enable!')

        elif not verify_crypto_deposit(transfer):
            status = INIT
            transfer.add_comment('init reason: crypto verify failed!')

        if status == INIT:
            send_system_message("Verify deposit: %s" % transfer, link=url_to_admin_list(
                transfer, {'status__exact': 'init', 'deposit': True}
            ))

        transfer.change_status(status)

        return transfer


class DepositTransferUpdateView(CreateAPIView, UserPassesTestMixin):
    authentication_classes = [CustomTokenAuthentication]
    serializer_class = DepositSerializer

    def test_func(self):
        permission_check = self.request.user.has_perm('ledger.add_transfer') and\
                           self.request.user.has_perm('ledger.change_transfer')
        return permission_check
