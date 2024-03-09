from decimal import Decimal
from uuid import uuid4

import django_filters
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from ledger.exceptions import SmallDepthError, InsufficientBalance
from ledger.models import MarginPosition, MarginHistoryModel, Wallet
from ledger.models.asset import AssetSerializerMini
from ledger.utils.external_price import SHORT, LONG, SELL, BUY
from ledger.utils.precision import floor_precision, get_margin_coin_presentation_balance
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import Order, PairSymbol
from market.serializers.symbol_serializer import SymbolSerializer
from market.utils.order_utils import new_order


class MarginPositionSerializer(AssetSerializerMini):
    symbol = SymbolSerializer()
    margin_ratio = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    base_debt = serializers.SerializerMethodField()
    asset_debt = serializers.SerializerMethodField()
    base_total = serializers.SerializerMethodField()
    asset_total = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    free_amount = serializers.SerializerMethodField()
    coin_amount = serializers.SerializerMethodField()
    liquidation_price = serializers.SerializerMethodField()
    pnl = serializers.SerializerMethodField()
    average_price = serializers.SerializerMethodField()
    current_price = serializers.SerializerMethodField()
    volume = serializers.SerializerMethodField()

    def get_margin_ratio(self, instance: MarginPosition):
        debt = Decimal(self.get_base_debt(instance))
        total = Decimal(self.get_base_total(instance))

        if debt:
            ratio = total / -debt
            if ratio > 0:
                return floor_precision(ratio, 2)
            return 1000

        return None

    def get_balance(self, instance):
        return get_margin_coin_presentation_balance(instance.symbol.base_asset.symbol, instance.equity)

    def get_loan_wallet(self, instance):
        if instance.side == SHORT:
            wallet = instance.asset_wallet
        else:
            wallet = instance.base_wallet
        return wallet

    def get_margin_wallet(self, instance):
        if instance.side == LONG:
            wallet = instance.asset_wallet
        else:
            wallet = instance.base_wallet
        return wallet

    def get_base_debt(self, instance):
        balance = self.get_loan_wallet(instance).balance

        if instance.side == SHORT:
            balance *= instance.symbol.last_trade_price

        return get_margin_coin_presentation_balance(instance.symbol.base_asset.symbol, balance)

    def get_asset_debt(self, instance):
        return get_margin_coin_presentation_balance(instance.symbol.asset.symbol, self.get_loan_wallet(instance).balance)

    def get_base_total(self, instance):
        balance = self.get_margin_wallet(instance).balance

        if instance.side == LONG:
            balance *= instance.symbol.last_trade_price

        return get_margin_coin_presentation_balance(instance.symbol.base_asset.symbol, balance)

    def get_asset_total(self, instance):
        return get_margin_coin_presentation_balance(instance.symbol.asset.symbol, self.get_margin_wallet(instance).balance)

    def get_amount(self, instance):
        amount = floor_precision(abs(instance.asset_wallet.balance), instance.symbol.step_size)
        amount *= -1 if instance.side == SHORT else 1
        return amount

    def get_free_amount(self, instance):
        return floor_precision(abs(instance.asset_wallet.get_free()), instance.symbol.step_size)

    def get_liquidation_price(self, instance):
        return floor_precision(instance.liquidation_price, instance.symbol.tick_size)

    def get_average_price(self, instance):
        return floor_precision(instance.average_price, instance.symbol.tick_size)

    def get_coin_amount(self, instance):
        return floor_precision(abs(instance.asset_wallet.balance), instance.symbol.step_size)

    def get_pnl(self, instance: MarginPosition):
        unrealised_pnl = (instance.base_total_balance + instance.base_debt_amount) - instance.equity
        return get_margin_coin_presentation_balance(instance.symbol.base_asset.symbol, unrealised_pnl)

    def get_current_price(self, instance):
        return instance.symbol.last_trade_price

    def get_volume(self, instance):
        amount = instance.asset_wallet.balance
        amount *= -1 if instance.side == SHORT else 1
        return get_margin_coin_presentation_balance(instance.symbol.base_asset.symbol, self.get_current_price(instance) * amount)

    class Meta:
        model = MarginPosition
        fields = ('created', 'account', 'asset_wallet', 'base_wallet', 'symbol', 'amount', 'free_amount',
                  'average_price', 'liquidation_price', 'side', 'status', 'id', 'margin_ratio', 'balance', 'base_debt',
                  'asset_debt', 'leverage', 'coin_amount', 'pnl', 'current_price', 'volume', 'equity', 'base_total',
                  'asset_total')


class MarginPositionFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name='symbol__name', lookup_expr='iexact')
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte')
    created = django_filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = MarginPosition
        fields = ('symbol', 'status', 'created_after')


class MarginPositionViewSet(ModelViewSet):
    serializer_class = MarginPositionSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = MarginPositionFilter

    def get_queryset(self):
        return MarginPosition.objects.filter(
            account=self.request.user.get_account(),
            liquidation_price__isnull=False,
            status=MarginPosition.OPEN
        ).order_by('-created').prefetch_related('base_wallet', 'asset_wallet', 'symbol', 'symbol__base_asset',
                                                'symbol__asset')


class MarginClosePositionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    percentage = serializers.IntegerField(min_value=1, max_value=100, default=100, required=False)

    def __init__(self, *args, **kwargs):
        super(MarginClosePositionSerializer, self).__init__(*args, **kwargs)

        self.position = MarginPosition.objects.filter(id=kwargs.get('data', {})['id'], status=MarginPosition.OPEN).first()

    def validate(self, attrs):
        if not self.position:
            raise ValidationError(
                {'id': _('there is no open position with this Id.')}
            )

        return attrs


class MarginClosePositionView(APIView):
    def post(self, request):
        serializer = MarginClosePositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        position = serializer.position

        queryset = Order.objects.filter(
            status=Order.NEW,
            account=position.account,
            symbol=position.symbol,
            wallet__market=position.asset_wallet.MARGIN
        )
        Order.cancel_orders(queryset)

        try:
            with WalletPipeline() as pipeline:
                # PairSymbol.objects.select_for_update().get(id=position.symbol_id)
                # position.liquidate(pipeline=pipeline, charge_insurance=False)

                amount = abs(position.asset_wallet.balance)
                if position.side == SHORT:
                    side = BUY
                else:
                    side = SELL

                price = Order.get_market_price(position.symbol, Order.get_opposite_side(side))
                if price:
                    if side == BUY:
                        price *= Decimal('0.95')
                    else:
                        price *= Decimal('1.05')
                    price = floor_precision(price, position.symbol.step_size)

                amount = position.asset_wallet.balance * serializer.data.get('percentage', 100) / 100

                new_order(
                    pipeline=pipeline,
                    symbol=position.symbol,
                    account=position.account,
                    amount=amount,
                    fill_type=Order.MARKET,
                    side=side,
                    market=Wallet.MARGIN,
                    variant=position.group_id,
                    pass_min_notional=True,
                    order_type=Order.ORDINARY,
                    parent_lock_group_id=uuid4(),
                    margin_position=position,
                    price=price
                )

                return Response(200)
        except SmallDepthError:
            return Response({'Error': 'به علت عمق کم بازار معامله انجام نشد'}, 400)
        except InsufficientBalance:
            return Response({'Error': 'Insufficient Balance'}, 400)
        return Response(200)
