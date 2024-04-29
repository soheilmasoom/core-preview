from decimal import Decimal
from uuid import uuid4

import django_filters
from django.db.models import Sum, F, Q
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import SystemConfig
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
    deadline = serializers.SerializerMethodField()

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

    def get_deadline(self, instance):
        if instance.liquidation_price:
            sys = SystemConfig.get_system_config()
            return instance.created + sys.position_deadline
        return None

    class Meta:
        model = MarginPosition
        fields = ('created', 'account', 'asset_wallet', 'base_wallet', 'symbol', 'amount', 'free_amount',
                  'average_price', 'liquidation_price', 'side', 'status', 'id', 'margin_ratio', 'balance', 'base_debt',
                  'asset_debt', 'leverage', 'coin_amount', 'pnl', 'current_price', 'volume', 'equity', 'base_total',
                  'asset_total', 'deadline')


class MarginPositionDetailedSerializer(MarginPositionSerializer):
    closed_time = serializers.SerializerMethodField()
    average_closed_price = serializers.SerializerMethodField()
    closed_volume = serializers.SerializerMethodField()
    closing_pnl = serializers.SerializerMethodField()

    def get_closing_side(self, instance):
        return BUY if instance.side == SHORT else SELL

    def get_closing_orders(self, instance):
        return instance.order_set.filter(side=self.get_closing_side(instance), filled_amount__gt=0)

    def get_closed_time(self, instance: MarginPosition):
        if instance.status == MarginPosition.CLOSED:
            last_trade = instance.trade_set.filter(side=self.get_closing_side(instance)).order_by('-created').first()
            return last_trade and last_trade.created
        return None

    def get_average_closed_price(self, instance: MarginPosition):
        return self.get_closing_orders(instance). \
            annotate(value=F('filled_amount') * F('price')). \
            aggregate(sum=Sum('value') / Sum('filled_amount'))['sum'] or 0

    def get_closed_volume(self, instance: MarginPosition):
        return self.get_closing_orders(instance).aggregate(sum=Sum('filled_amount'))['sum'] or 0

    def get_closing_pnl(self, instance: MarginPosition):
        return instance.marginhistorymodel_set.filter(type=MarginHistoryModel.PNL).aggregate(sum=Sum('amount'))['sum'] or 0

    class Meta:
        model = MarginPosition
        fields = (*MarginPositionSerializer.Meta.fields, 'closed_time', 'average_closed_price', 'closing_pnl', 'closed_volume', )


class MarginPositionFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name='symbol__name', lookup_expr='iexact')
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte')
    created = django_filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = MarginPosition
        fields = ('symbol', 'status', 'created_after')


class MarginPositionViewSet(ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filter_class = MarginPositionFilter

    def get_serializer_class(self):
        if self.request.GET.get('stat') == '1':
            return MarginPositionDetailedSerializer
        return MarginPositionSerializer

    def get_queryset(self):
        stat = self.request.GET.get('stat', '0')
        queryset = MarginPosition.objects.filter(
            account=self.request.user.get_account(),
            liquidation_price__isnull=False,
        )
        prefetch_fields = ['base_wallet', 'asset_wallet', 'symbol', 'symbol__base_asset', 'symbol__asset']

        if stat == '0':
            queryset = queryset.filter(status=MarginPosition.OPEN)
        elif stat == '1':
            queryset = queryset.filter(
                Q(trade__isnull=False) | Q(status=MarginPosition.OPEN, liquidation_price__isnull=False)
            )
            prefetch_fields.extend(['order_set', 'trade_set', 'marginhistorymodel_set'])

        return queryset.order_by('-created').prefetch_related(*prefetch_fields)


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

        try:
            amount = abs(position.asset_wallet.balance) * serializer.data.get('percentage', 100) / 100
            position.close(amount=amount)
            return Response(200)

        except SmallDepthError:
            return Response({'Error': 'به علت عمق کم بازار معامله انجام نشد'}, 400)
        except InsufficientBalance:
            return Response({'Error': 'Insufficient Balance'}, 400)
        return Response(200)
