import logging
from datetime import timedelta

from django.db.models import Max, Min, Sum, F
from django.utils import timezone
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from accounts.models import Account
from ledger.models import Asset
from ledger.models.asset import AssetSerializerMini
from ledger.utils.external_price import BUY
from ledger.utils.precision import get_presentation_amount, floor_precision, decimal_to_str
from market.models import PairSymbol, Trade, Order
from market.utils.price import get_symbol_prices

logger = logging.getLogger(__name__)


class SymbolSerializer(serializers.ModelSerializer):
    asset = AssetSerializerMini(read_only=True)
    base_asset = AssetSerializerMini(read_only=True)
    bookmark = serializers.SerializerMethodField()

    maker_fee = serializers.SerializerMethodField()
    taker_fee = serializers.SerializerMethodField()

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ('min_trade_quantity', 'max_trade_quantity'):
            representation[field] = get_presentation_amount(representation[field])
        return representation

    def get_bookmark(self, pair_symbol: PairSymbol):
        return pair_symbol.id in self.context.get('bookmarks', [])

    def get_maker_fee(self, pair_symbol: PairSymbol):
        return '0'

    def get_taker_fee(self, pair_symbol: PairSymbol):
        return '0.002'

    class Meta:
        model = PairSymbol
        fields = ('id', 'name', 'asset', 'base_asset', 'taker_fee', 'maker_fee', 'tick_size', 'step_size',
                  'min_trade_quantity', 'max_trade_quantity', 'enable', 'bookmark', 'margin_enable', 'strategy_enable',)


class SymbolBriefStatsSerializer(serializers.ModelSerializer):
    asset = AssetSerializerMini(read_only=True)
    base_asset = AssetSerializerMini(read_only=True)
    price = serializers.SerializerMethodField()
    change_percent = serializers.SerializerMethodField()
    bookmark = serializers.SerializerMethodField()

    maker_fee = serializers.SerializerMethodField()
    taker_fee = serializers.SerializerMethodField()

    max_leverage = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.prices_data_dic = self.context.get('prices')
        if not self.prices_data_dic:
            self.prices_data_dic = get_symbol_prices()

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ('min_trade_quantity', 'max_trade_quantity'):
            serializer_field = representation.get(field)
            if serializer_field:
                representation[field] = get_presentation_amount(serializer_field)
        return representation

    def get_price(self, symbol: PairSymbol):
        last_prices = self.prices_data_dic['last']
        price = last_prices.get(symbol.id)
        if price:
            return decimal_to_str(floor_precision(price, symbol.tick_size))

    def get_bookmark(self, pair_symbol: PairSymbol):
        return pair_symbol.id in self.context.get('bookmarks', [])

    def get_change_value_pairs(self, symbol: PairSymbol):
        yesterday_prices = self.prices_data_dic['yesterday']
        today_prices = self.prices_data_dic['last']

        previous_trade_price = yesterday_prices.get(symbol.id)
        last_trade_price = today_prices.get(symbol.id)

        if not previous_trade_price or not last_trade_price:
            return None, None

        return last_trade_price, previous_trade_price

    def get_change_percent(self, symbol: PairSymbol):
        last_price, previous_price = self.get_change_value_pairs(symbol)
        if not (last_price and previous_price):
            return
        change_percent = 100 * (last_price - previous_price) / previous_price
        return decimal_to_str(floor_precision(change_percent, 2))

    def get_maker_fee(self, pair_symbol: PairSymbol):
        return '0'

    def get_taker_fee(self, pair_symbol: PairSymbol):
        return '0.002'

    def get_max_leverage(self, pair_symbol: PairSymbol):
        if pair_symbol.margin_enable:
            return self.context['system_config'].max_margin_leverage
        else:
            return 1

    class Meta:
        model = PairSymbol
        fields = ('name', 'asset', 'base_asset', 'enable', 'price', 'change_percent', 'bookmark', 'margin_enable',
                  'strategy_enable',  'taker_fee', 'maker_fee', 'tick_size', 'step_size', 'min_trade_quantity',
                  'max_trade_quantity', 'max_leverage')


class SymbolStatsSerializer(SymbolBriefStatsSerializer):
    change = serializers.SerializerMethodField()
    high = serializers.SerializerMethodField()
    low = serializers.SerializerMethodField()
    volume = serializers.SerializerMethodField()
    base_volume = serializers.SerializerMethodField()
    bookmark = serializers.SerializerMethodField()

    def get_change(self, symbol: PairSymbol):
        last_price, previous_price = self.get_change_value_pairs(symbol)
        if not (last_price and previous_price):
            return
        return decimal_to_str(floor_precision((last_price - previous_price), symbol.tick_size))

    def get_high(self, symbol: PairSymbol):
        high_price = Trade.objects.filter(
            symbol=symbol,
            created__gt=timezone.now() - timedelta(hours=24),
            created__lte=timezone.now(),
        ).aggregate(max_price=Max('price'))['max_price']
        if high_price:
            return decimal_to_str(floor_precision(high_price, symbol.tick_size))

    def get_low(self, symbol: PairSymbol):
        low_price = Trade.objects.filter(
            symbol=symbol,
            created__gt=timezone.now() - timedelta(hours=24),
            created__lte=timezone.now(),
        ).aggregate(min_price=Min('price'))['min_price']
        if low_price:
            return decimal_to_str(floor_precision(low_price, symbol.tick_size))

    def get_volume(self, symbol: PairSymbol):
        total_amount = Trade.objects.filter(
            symbol=symbol,
            created__gt=timezone.now() - timedelta(hours=24),
            created__lte=timezone.now(),
            side=BUY,
        ).aggregate(total_amount=Sum('amount'))['total_amount']

        if total_amount:
            return decimal_to_str(floor_precision(total_amount, symbol.step_size))

    def get_base_volume(self, symbol: PairSymbol):
        total_amount = Trade.objects.filter(
            symbol=symbol,
            created__gt=timezone.now() - timedelta(hours=24),
            created__lte=timezone.now(),
            side=BUY,
        ).aggregate(total_amount=Sum(F('amount') * F('price')))['total_amount']

        if total_amount:
            return decimal_to_str(floor_precision(total_amount))

    def get_bookmark(self, pair_symbol: PairSymbol):
        user = self.context['request'].user

        if user.is_authenticated:
            return user.get_account().bookmark_market.filter(id=pair_symbol.id).exists()
        else:
            return False

    class Meta:
        model = PairSymbol
        fields = ('name', 'asset', 'base_asset', 'enable', 'price', 'change', 'change_percent',
                  'high', 'low', 'volume', 'base_volume', 'bookmark')


class BookMarkPairSymbolSerializer(serializers.ModelSerializer):
    pair_symbol = serializers.CharField()
    action = serializers.CharField()

    def update(self, instance, validated_data):
        pair_symbol = get_object_or_404(PairSymbol, name=validated_data.get('pair_symbol'), enable=True)
        action = validated_data['action']
        if action == 'add':
            instance.account.bookmark_market.add(pair_symbol)
        elif action == 'remove':
            instance.account.bookmark_market.remove(pair_symbol)
        instance.save()
        return instance

    class Meta:
        model = Account
        fields = ['pair_symbol', 'action', ]
