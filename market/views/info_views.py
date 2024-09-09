from decimal import Decimal

from rest_framework import serializers
from rest_framework.generics import ListAPIView

from ledger.models.asset import Asset
from ledger.utils.external_price import SELL, BUY
from ledger.utils.precision import get_symbol_presentation_price
from ledger.utils.price import get_prices


class AssetListSerializer(serializers.ModelSerializer):
    ask = serializers.SerializerMethodField()
    bid = serializers.SerializerMethodField()

    def get_ask(self, asset: Asset):
        base = self.context['base']
        symbol = asset.symbol + base
        asks = self.context['asks']
        return get_symbol_presentation_price(symbol, asks.get(symbol))

    def get_bid(self, asset: Asset):
        base = self.context['base']
        symbol = asset.symbol + base
        bids = self.context['bids']
        return get_symbol_presentation_price(symbol, bids.get(symbol))

    class Meta:
        model = Asset
        fields = ('symbol', 'ask', 'bid', 'name')
        ref_name = 'market asset'


class MarketIRTInfoView(ListAPIView):
    queryset = Asset.live_objects.filter(otc_status__in=Asset.OTC_TRADE_ACTIVE_STATUSES).exclude(symbol=Asset.IRT)
    serializer_class = AssetListSerializer
    authentication_classes = []
    permission_classes = []

    BASE = Asset.IRT

    def get_serializer_context(self):
        ctx = super().get_serializer_context()

        coins = list(self.get_queryset().values_list('symbol', flat=True))

        bids = get_prices([coin + self.BASE for coin in coins], side=BUY, allow_stale=True)
        asks = get_prices([coin + self.BASE for coin in coins], side=SELL, allow_stale=True)

        asks[self.BASE + self.BASE] = bids[self.BASE + self.BASE] = Decimal(1)

        return {
            **ctx,
            'asks': asks,
            'bids': bids,
            'base': self.BASE
        }


class MarketUSDTInfoView(MarketIRTInfoView):
    BASE = Asset.USDT
