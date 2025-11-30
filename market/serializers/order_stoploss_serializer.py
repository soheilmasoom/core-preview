import logging
from decimal import Decimal
from typing import Union

from rest_framework import serializers

from ledger.models import Wallet
from ledger.utils.external_price import BUY, SELL
from ledger.utils.precision import floor_precision, decimal_to_str
from market.models import Order, StopLoss

logger = logging.getLogger(__name__)


class OrderStopLossSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source='symbol.name')
    id = serializers.SerializerMethodField()
    filled_amount = serializers.SerializerMethodField()
    filled_percent = serializers.SerializerMethodField()
    filled_price = serializers.SerializerMethodField()
    trigger_price = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    is_oco = serializers.SerializerMethodField()
    market = serializers.CharField(source='wallet.market', default=Wallet.SPOT)
    allow_cancel = serializers.SerializerMethodField()
    leverage = serializers.SerializerMethodField()
    position_side = serializers.SerializerMethodField()

    def to_representation(self, instance: Union[Order, StopLoss]):
        data = super(OrderStopLossSerializer, self).to_representation(instance)
        data['amount'] = decimal_to_str(
            floor_precision(Decimal(data['amount']), instance.symbol.step_size),
            truncate=False
        )

        if data['price']:
            data['price'] = decimal_to_str(
                floor_precision(Decimal(data['price']), instance.symbol.tick_size),
                truncate=False
            )

        data['symbol'] = instance.symbol.name

        return data

    def get_id(self, instance: Union[Order, StopLoss]):
        if isinstance(instance, StopLoss):
            return f'sl-{instance.id}'
        return str(instance.id)

    def get_allow_cancel(self, instance: Union[Order, StopLoss]):
        if instance.wallet.is_for_strategy:
            return False
        return True

    def get_status(self, instance: Union[Order, StopLoss]):
        if isinstance(instance, StopLoss):
            if not instance.order_set.exists():
                return StopLoss.NEW
            else:
                return StopLoss.FILLED if instance.filled_amount == instance.amount else StopLoss.TRIGGERED
        return instance.status

    def get_is_oco(self, instance: Union[Order, StopLoss]):
        return bool(instance.oco)

    def get_filled_amount(self, instance: Union[Order, StopLoss]):
        return decimal_to_str(floor_precision(instance.filled_amount, instance.symbol.step_size))

    def get_filled_percent(self, instance: Union[Order, StopLoss]):
        return decimal_to_str(floor_precision(100 * instance.filled_amount / instance.amount, 0)) + '%'

    def get_trigger_price(self, instance: Union[Order, StopLoss]):
        if isinstance(instance, Order):
            return None

        price = decimal_to_str(floor_precision(instance.trigger_price, instance.symbol.tick_size))
        operator = '≥' if instance.side == SELL else '≤'
        return f'{price} {operator} آخرین قیمت'

    def get_filled_price(self, instance: Union[Order, StopLoss]):
        order = instance if isinstance(instance, Order) else instance.order_set.all().first()

        if not order:
            return

        fills_amount, fills_value = self.context['trades'].get(order.id, (0, 0))
        amount = Decimal((fills_amount or 0))

        if not amount:
            return

        price = Decimal((fills_value or 0)) / amount
        return decimal_to_str(floor_precision(price, order.symbol.tick_size))

    def get_leverage(self, instance):
        if isinstance(instance, Order):
            return instance.position and instance.position.leverage
        return None

    def get_position_side(self, instance: Order):
        if isinstance(instance, Order):
            return instance.position and instance.position.side
        return None

    class Meta:
        model = Order
        fields = ('id', 'created', 'wallet', 'symbol', 'amount', 'filled_amount', 'filled_percent', 'price',
                  'filled_price', 'trigger_price', 'side', 'fill_type', 'status', 'market', 'allow_cancel', 'is_oco',
                  'leverage', 'position_side')
