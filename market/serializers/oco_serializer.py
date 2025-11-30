import logging
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from accounts.models import LoginActivity
from ledger.exceptions import InsufficientBalance
from ledger.models import Wallet
from ledger.utils.external_price import BUY
from ledger.utils.precision import floor_precision, decimal_to_str
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import Order, PairSymbol, OCO, StopLoss
from market.serializers.order_serializer import OrderSerializer
from market.utils.order_utils import new_order

logger = logging.getLogger(__name__)


class OCOSerializer(OrderSerializer):
    id = serializers.IntegerField(read_only=True)
    symbol = serializers.CharField(source='symbol.name')
    filled_amount = serializers.SerializerMethodField()
    completed = serializers.SerializerMethodField()
    market = serializers.CharField(source='wallet.market', default=Wallet.SPOT)
    stop_loss_price = serializers.DecimalField(max_digits=18, decimal_places=8)
    stop_loss_trigger_price = serializers.DecimalField(max_digits=18, decimal_places=8)

    def get_completed(self, oco: OCO):
        return oco.filled_amount == oco.amount

    def to_representation(self, oco: OCO):
        data = super(OrderSerializer, self).to_representation(oco)
        data['amount'] = decimal_to_str(floor_precision(Decimal(data['amount']), oco.symbol.step_size))
        if data['price']:
            data['price'] = decimal_to_str(floor_precision(Decimal(data['price']), oco.symbol.tick_size))
        data['stop_loss_price'] = decimal_to_str(
            floor_precision(Decimal(data['stop_loss_price']), oco.symbol.tick_size))
        data['stop_loss_trigger_price'] = decimal_to_str(
            floor_precision(Decimal(data['stop_loss_trigger_price']), oco.symbol.tick_size))
        data['symbol'] = oco.symbol.name
        return data

    def create(self, validated_data):
        symbol = get_object_or_404(PairSymbol, name=validated_data['symbol']['name'].upper(), enable=True)
        validated_data['price'] = self.post_validate_price(symbol, validated_data['price'])
        validated_data['stop_loss_price'] = self.post_validate_price(symbol, validated_data['stop_loss_price'])
        validated_data['stop_loss_trigger_price'] = self.post_validate_price(
            symbol, validated_data['stop_loss_trigger_price'])

        order_price = min(validated_data['price'], validated_data['stop_loss_price'])
        wallet = self.post_validate(symbol, {**validated_data, 'price': order_price})
        try:
            with WalletPipeline() as pipeline:
                lock_amount = Order.get_to_lock_amount(
                    validated_data['amount'],
                    max(validated_data['price'], validated_data['stop_loss_price']),
                    validated_data['side'],
                    wallet.market
                )
                releasable_lock = Decimal(0)
                if validated_data['side'] == BUY:
                    releasable_lock = (validated_data['stop_loss_price'] - validated_data['price']) * validated_data['amount']
                base_wallet = symbol.base_asset.get_wallet(wallet.account, wallet.market)
                lock_wallet = Order.get_to_lock_wallet(wallet, base_wallet, validated_data['side'], symbol)
                if lock_wallet.has_balance(lock_amount, raise_exception=True):
                    login_activity = LoginActivity.from_request(request=self.context['request'])

                    instance = super(OrderSerializer, self).create(
                        {**validated_data,
                         'wallet': wallet, 'symbol': symbol, 'releasable_lock': releasable_lock, 'login_activity': login_activity}
                    )
                    instance.acquire_lock(lock_wallet, lock_amount, pipeline)
                    order = new_order(
                        pipeline=pipeline,
                        symbol=instance.symbol,
                        account=instance.wallet.account,
                        amount=instance.amount,
                        price=instance.price,
                        side=instance.side,
                        fill_type=Order.LIMIT,
                        raise_exception=False,
                        market=instance.wallet.market,
                        parent_lock_group_id=instance.group_id,
                        oco_id=instance.id
                    )
                    if not order.trades:
                        StopLoss.objects.create(
                            wallet=instance.wallet,
                            symbol=instance.symbol,
                            amount=instance.amount,
                            price=instance.stop_loss_price,
                            trigger_price=instance.stop_loss_trigger_price,
                            side=instance.side,
                            fill_type=StopLoss.LIMIT,
                            group_id=instance.group_id,
                            oco_id=instance.id
                        )
                    return instance
        except InsufficientBalance:
            raise ValidationError(_('Insufficient Balance'))

    def validate(self, attrs):
        return super(OrderSerializer, self).validate(attrs)

    class Meta:
        model = OCO
        fields = ('id', 'created', 'wallet', 'symbol', 'amount', 'filled_amount', 'price', 'stop_loss_price', 'stop_loss_trigger_price', 'side',
                  'completed', 'market', 'canceled_at')
        read_only_fields = ('id', 'created', 'canceled_at')
        extra_kwargs = {
            'wallet': {'write_only': True, 'required': False},
        }
