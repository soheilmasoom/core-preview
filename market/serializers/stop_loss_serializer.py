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
from market.models import StopLoss, Order, PairSymbol
from market.serializers.order_serializer import OrderSerializer

logger = logging.getLogger(__name__)


class StopLossSerializer(OrderSerializer):
    id = serializers.IntegerField(read_only=True)
    symbol = serializers.CharField(source='symbol.name')
    filled_amount = serializers.SerializerMethodField()
    completed = serializers.SerializerMethodField()
    market = serializers.CharField(source='wallet.market', default=Wallet.SPOT)
    trigger_price = serializers.DecimalField(max_digits=18, decimal_places=8)

    def get_completed(self, stop_loss: StopLoss):
        return stop_loss.filled_amount == stop_loss.amount

    def to_representation(self, stop_loss: StopLoss):
        data = super(OrderSerializer, self).to_representation(stop_loss)
        data['amount'] = decimal_to_str(floor_precision(Decimal(data['amount']), stop_loss.symbol.step_size))
        if data['price']:
            data['price'] = decimal_to_str(floor_precision(Decimal(data['price']), stop_loss.symbol.tick_size))
        data['trigger_price'] = decimal_to_str(floor_precision(Decimal(data['trigger_price']), stop_loss.symbol.tick_size))
        data['symbol'] = stop_loss.symbol.name
        return data

    def create(self, validated_data):
        symbol = get_object_or_404(PairSymbol, name=validated_data['symbol']['name'].upper(), enable=True)
        if validated_data.get('price'):
            conservative_factor = Decimal(1)
            validated_data['price'] = self.post_validate_price(symbol, validated_data['price'])
        else:
            conservative_factor = Decimal('1.01') if validated_data['side'] == BUY else Decimal(1)
        
        order_price = validated_data.get('price', validated_data['trigger_price']) * conservative_factor
        wallet = self.post_validate(symbol, {**validated_data, 'price': validated_data.get('price', order_price)})
        validated_data['trigger_price'] = self.post_validate_price(symbol, validated_data['trigger_price'])
        try:
            with WalletPipeline() as pipeline:
                lock_amount = Order.get_to_lock_amount(
                    validated_data['amount'], order_price, validated_data['side'], wallet.market
                )
                base_wallet = symbol.base_asset.get_wallet(wallet.account, wallet.market)
                lock_wallet = Order.get_to_lock_wallet(wallet, base_wallet, validated_data['side'], symbol)
                if lock_wallet.has_balance(lock_amount, raise_exception=True):
                    login_activity = LoginActivity.from_request(request=self.context['request'])

                    instance = super(OrderSerializer, self).create(
                        {**validated_data, 'wallet': wallet, 'symbol': symbol, 'login_activity': login_activity}
                    )
                    instance.acquire_lock(lock_wallet, lock_amount, pipeline)
                    return instance
        except InsufficientBalance:
            raise ValidationError(_('Insufficient Balance'))

    def validate(self, attrs):
        if attrs.get('market') == Wallet.MARGIN:
            raise ValidationError(_('در بازار تعهدی امکان سفارش oco وجود ندارد'))
        return super(StopLossSerializer, self).validate(attrs)

    class Meta:
        model = StopLoss
        fields = ('id', 'created', 'wallet', 'symbol', 'amount', 'filled_amount', 'price', 'trigger_price', 'side',
                  'fill_type', 'completed', 'market', 'canceled_at')
        read_only_fields = ('id', 'created', 'canceled_at')
        extra_kwargs = {
            'wallet': {'write_only': True, 'required': False},
        }
