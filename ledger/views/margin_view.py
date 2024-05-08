from decimal import Decimal

import django_filters
from django.db.models import F, Sum, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import SystemConfig
from ledger.exceptions import InsufficientBalance
from ledger.margin.margin_info import MarginInfo
from ledger.models import MarginTransfer, Asset, Wallet, MarginPosition, MarginLeverage
from ledger.models.asset import CoinField, AssetSerializerMini
from ledger.models.margin import SymbolField
from ledger.models.position import MarginHistoryModel
from ledger.utils.external_price import LONG, USDT
from ledger.utils.fields import get_serializer_amount_field
from ledger.utils.margin import check_margin_view_permission
from ledger.utils.precision import floor_precision, get_presentation_amount, get_margin_coin_presentation_balance
from ledger.utils.price import get_last_price, get_last_prices, get_coins_symbols


class MarginInfoView(APIView):

    @staticmethod
    def aggregate_wallets_values(wallets, prices):
        total_irt_value = total_usdt_value = Decimal(0)
        for wallet in wallets:
            coin = wallet.asset.symbol
            price_usdt = prices.get(coin + Asset.USDT, 0)
            price_irt = prices.get(coin + Asset.IRT, 0)

            total_usdt_value += wallet.balance * price_usdt
            total_irt_value += wallet.balance * price_irt
        return {
            'IRT': get_presentation_amount(floor_precision(total_irt_value)),
            'USDT': get_presentation_amount(floor_precision(total_usdt_value, 8))
        }

    def get(self, request: Request):
        account = request.user.get_account()

        user_margin_wallets = Wallet.objects.filter(
            Q(variant__isnull=True) | Q(asset_wallet__status=MarginPosition.OPEN) | Q(base_wallet__status=MarginPosition.OPEN),
            account=account, market=Wallet.MARGIN)

        coins = list(user_margin_wallets.values_list('asset__symbol', flat=True))
        prices = get_last_prices(get_coins_symbols(coins))

        total_asset = self.aggregate_wallets_values(user_margin_wallets.filter(balance__gt=Decimal('0')), prices)
        total_debt = self.aggregate_wallets_values(user_margin_wallets.filter(balance__lt=Decimal('0')), prices)

        return Response({
            'total_assets': total_asset,
            'total_equity': {
                'IRT': get_margin_coin_presentation_balance('IRT', Decimal(total_asset['IRT']) + Decimal(total_debt['IRT'])),
                'USDT': get_margin_coin_presentation_balance('USDT', Decimal(total_asset['USDT']) + Decimal(total_debt['USDT'])),
            }
        })


class AssetMarginInfoView(APIView):
    def get(self, request: Request, symbol):
        account = request.user.get_account()
        asset = get_object_or_404(Asset, symbol=symbol.upper())

        margin_info = MarginInfo.get(account)

        margin_wallet = asset.get_wallet(account, Wallet.MARGIN)
        loan_wallet = asset.get_wallet(account, Wallet.LOAN)

        price = get_last_price(asset.symbol + Asset.USDT)

        if asset.symbol != Asset.USDT:
            price = price * Decimal('1.002')

        max_borrow = max(margin_info.get_max_borrowable() / price, Decimal(0))
        max_transfer = min(margin_wallet.get_free(), max(margin_info.get_max_transferable() / price, Decimal(0)))

        return Response({
            'balance': margin_wallet.get_free(),
            'debt': -loan_wallet.get_free(),
            'max_borrow': max_borrow,
            'max_transfer': max_transfer,
        })


class MarginTransferSerializer(serializers.ModelSerializer):
    amount = get_serializer_amount_field()
    coin = CoinField(source='asset')
    symbol = SymbolField(source='position_symbol', required=False)
    asset = AssetSerializerMini(read_only=True)
    id = serializers.IntegerField(write_only=True, required=False)

    def validate(self, attrs):
        user = self.context['request'].user
        symbol = attrs.get('position_symbol')
        check_margin_view_permission(user.get_account(), symbol)

        if attrs['asset'] not in Asset.objects.filter(symbol__in=[Asset.IRT, Asset.USDT]):
            raise ValidationError({'asset': 'فقط میتوانید ریال و تتر انتقال دهید.'})

        if attrs['type'] not in [MarginTransfer.SPOT_TO_MARGIN, MarginTransfer.MARGIN_TO_SPOT] and not symbol:
            raise ValidationError({'symbol': 'بازار را وارد کنید'})

        if attrs['type'] in [MarginTransfer.POSITION_TO_MARGIN, MarginTransfer.MARGIN_TO_POSITION]:
            if symbol.base_asset != attrs['asset']:
                asset = symbol.base_asset.name_fa
                raise ValidationError({'asset': f'فقط میتوانید {asset} انتقال دهید.'})

            if not attrs.get('id'):
                raise ValidationError({'id': 'id موقعیت را وارد کنید'})

            position = MarginPosition.objects.filter(
                account=user.get_account(),
                symbol=symbol,
                status__in=[MarginPosition.OPEN],
                id=attrs.pop('id')
            ).first()

            if not position:
                raise ValidationError('There is no valid position to transfer margin')
            attrs['position'] = position

            if attrs['type'] == MarginTransfer.POSITION_TO_MARGIN and position.withdrawable_base_asset < Decimal(attrs['amount']):
                raise ValidationError(f'فقط میتوانید {position.withdrawable_base_asset} انتقال دهید')

            if attrs['type'] == MarginTransfer.MARGIN_TO_POSITION and position.side == LONG and position.debt_amount < Decimal(attrs['amount']):
                raise ValidationError(f'فقط میتوانید {position.debt_amount} انتقال دهید')

        return attrs

    class Meta:
        model = MarginTransfer
        fields = ('created', 'amount', 'type', 'coin', 'asset', 'symbol', 'id', 'position')
        read_only_fields = ('created', )


class MarginTransferViewSet(ModelViewSet):
    serializer_class = MarginTransferSerializer
    pagination_class = LimitOffsetPagination

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['type']

    def perform_create(self, serializer):
        try:
            serializer.save(account=self.request.user.get_account())
        except InsufficientBalance:
            raise ValidationError('موجودی کافی نیست.')

    def get_queryset(self):
        return MarginTransfer.objects.filter(
            account=self.request.user.get_account()
        ).order_by('-created')


class MarginPositionInfoView(APIView):
    def get(self, request: Request):
        account = request.user.get_account()
        symbol = request.GET.get('symbol')

        if not symbol:
            return Response({'Error': 'need symbol'}, 400)

        from market.models import PairSymbol

        symbol_model = get_object_or_404(PairSymbol, name=symbol, enable=True)

        free = symbol_model.base_asset.get_wallet(
            account, Wallet.MARGIN, None
        ).get_free()

        margin_leverage, _ = MarginLeverage.objects.get_or_create(account=account)

        user_total_equity = MarginPosition.objects.filter(
            account=account,
            status__in=[MarginPosition.TERMINATING, MarginPosition.OPEN],
            symbol__base_asset=symbol_model.base_asset
        ).annotate(base_asset_value=F('asset_wallet__balance') * F('symbol__last_trade_price')).\
            aggregate(total_equity=Sum('base_asset_value') + Sum('base_wallet__balance'))['total_equity'] or 0

        sys_config = SystemConfig.get_system_config()

        if symbol_model.base_asset.symbol == USDT:
            user_available_equity = sys_config.total_user_margin_usdt_base - user_total_equity
        else:
            user_available_equity = sys_config.total_user_margin_irt_base - user_total_equity

        user_available_equity = max(0, user_available_equity * Decimal('0.99'))

        data = {
            'max_buy_volume': min(free * margin_leverage.leverage, user_available_equity),
            'max_sell_volume': min(free * margin_leverage.leverage, user_available_equity) / symbol_model.last_trade_price,
        }

        data["max_buy_volume"] = get_margin_coin_presentation_balance(symbol_model.base_asset.symbol,
                                                                      max(Decimal('0'),
                                                                          data['max_buy_volume']) * Decimal('0.99'))
        data["max_sell_volume"] = get_margin_coin_presentation_balance(symbol_model.asset.symbol,
                                                                       max(Decimal('0'),
                                                                           data['max_sell_volume']) * Decimal('0.99'))
        return Response(data)


class MarginHistorySerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    symbol = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    def get_asset(self, instance):
        return instance.asset.symbol

    def get_symbol(self, instance):
        return instance.position and instance.position.symbol.name

    def get_amount(self, instance):
        return get_presentation_amount(instance.amount)

    class Meta:
        model = MarginHistoryModel
        fields = ('created', 'amount', 'symbol', 'type', 'position', 'asset')


class PositionFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name='position__symbol__name', lookup_expr='iexact')
    asset = django_filters.CharFilter(field_name='asset__symbol', lookup_expr='iexact')
    position = django_filters.CharFilter(field_name='position__id')

    class Meta:
        model = MarginHistoryModel
        fields = ('symbol', 'asset', 'type', 'position')


class MarginPositionHistoryView(ListAPIView):
    serializer_class = MarginHistorySerializer
    pagination_class = LimitOffsetPagination

    filter_backends = [DjangoFilterBackend]
    filter_class = PositionFilter

    def get_queryset(self):
        account = self.request.user.get_account()
        return MarginHistoryModel.objects.filter(account=account).order_by('-created')


class LeverageViewSerializer(serializers.ModelSerializer):

    def validate(self, attrs):
        max_leverage = self.context['request'].user.get_account().get_max_margin_leverage()

        if not 1 <= Decimal(attrs.get('leverage')) <= max_leverage:
            raise ValidationError(f'ضریب باید عددی صحیحی بین 1 و {max_leverage} باشد.')

        return attrs

    class Meta:
        model = MarginLeverage
        fields = ('leverage',)


class MarginLeverageView(APIView):
    def post(self, request):
        serializer = LeverageViewSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.data

        MarginLeverage.objects.update_or_create(
            account=request.user.account,
            defaults={
                'leverage': data['leverage']
            }
        )

        return Response(200)

    def get(self, request):
        margin_leverage, _ = MarginLeverage.objects.get_or_create(account=request.user.account)

        return Response({
            "leverage": margin_leverage.leverage,
            "max_leverage": request.user.get_account().get_max_margin_leverage()
        }, 200)

