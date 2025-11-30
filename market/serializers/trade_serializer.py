from decimal import Decimal

from rest_framework import serializers

from ledger.utils.external_price import BUY
from ledger.utils.precision import get_presentation_amount
from market.models import Trade


class AccountTradeSerializer(serializers.ModelSerializer):
    asset = serializers.CharField(source='symbol.asset.symbol')
    base_asset = serializers.CharField(source='symbol.base_asset.symbol')
    base_amount = serializers.SerializerMethodField()
    leverage = serializers.SerializerMethodField()
    position_side = serializers.SerializerMethodField()

    def get_base_amount(self, trade: Trade):
        return trade.price * trade.amount

    def get_leverage(self, trade: Trade):
        if isinstance(trade, Trade):
            return trade.position and trade.position.leverage
        return None

    def get_position_side(self, trade: Trade):
        if isinstance(trade, Trade):
            return trade.position and trade.position.side
        return None

    def to_representation(self, trade: Trade):
        data = super(AccountTradeSerializer, self).to_representation(trade)
        data['amount'] = get_presentation_amount(data['amount'])
        data['price'] = get_presentation_amount(data['price'])
        data['base_amount'] = get_presentation_amount(data['base_amount'])

        if 'fee_amount' in data:
            data['fee_amount'] = get_presentation_amount(data['fee_amount'])

            data['fee_asset'] = data['asset'] if data['side'] == BUY else data['base_asset']
        return data

    class Meta:
        model = Trade
        fields = ('id', 'created', 'asset', 'base_asset', 'side', 'amount', 'price', 'base_amount', 'fee_amount',
                  'market', 'leverage', 'position_side')


class TradeSerializer(serializers.ModelSerializer):
    is_buyer_maker = serializers.SerializerMethodField()

    @classmethod
    def get_is_buyer_maker(cls, instance: Trade):
        return (instance.side == BUY) == instance.is_maker

    class Meta:
        model = Trade
        fields = ('created', 'amount', 'price', 'is_buyer_maker')

    def to_representation(self, trade: Trade):
        data = super().to_representation(trade)

        amount = get_presentation_amount(Decimal(data['amount']), trade.symbol.step_size)

        if not amount:
            amount = get_presentation_amount(trade.symbol.min_trade_quantity, trade.symbol.step_size)

        data['amount'] = str(amount)
        data['price'] = get_presentation_amount(Decimal(data['price']), trade.symbol.tick_size, trunc_zero=False)

        return data


class TradePairSerializer(TradeSerializer):
    symbol = serializers.CharField(source='symbol.name')
    client_order_id = serializers.SerializerMethodField()
    pair_order_id = serializers.SerializerMethodField()
    pair_client_order_id = serializers.SerializerMethodField()

    def get_client_order_id(self, instance: Trade):
        return self.context['client_order_id_mapping'].get(instance.order_id)

    def get_pair_order_id(self, instance: Trade):
        mapping = self.context['maker_taker_mapping'].get(instance.group_id)
        if mapping:
            return mapping[1] if instance.is_maker else mapping[0]

    def get_pair_client_order_id(self, instance: Trade):
        return self.context['client_order_id_mapping'].get(self.get_pair_order_id(instance))

    class Meta:
        model = Trade
        fields = ('id', 'symbol', 'side', 'created', 'amount', 'price', 'is_maker', 'order_id', 'client_order_id',
                  'pair_order_id', 'pair_client_order_id')
