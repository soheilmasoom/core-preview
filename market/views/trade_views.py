from decimal import Decimal

import django_filters
from django.db.models import Min, Max, F, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.authentication import CustomJWTAuthentication, CustomTokenAuthentication
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from ledger.models.wallet import ReserveWallet
from market.models import Trade, PairSymbol, Order
from market.pagination import FastLimitOffsetPagination
from market.serializers.trade_serializer import TradePairSerializer, TradeSerializer, AccountTradeSerializer


class AccountTradeFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name='symbol__name', lookup_expr='iexact')

    class Meta:
        model = Trade
        fields = ('symbol', 'side', 'order_id')


class AccountTradeHistoryView(ListAPIView):
    authentication_classes = (SessionAuthentication, CustomJWTAuthentication)
    pagination_class = LimitOffsetPagination
    serializer_class = AccountTradeSerializer

    filter_backends = [DjangoFilterBackend]
    filter_class = AccountTradeFilter

    def get_queryset(self):
        trades = Trade.objects.filter(
            account=self.request.user.get_account(),
            status=Trade.DONE,
        )

        strategy = self.request.query_params.get('strategy')
        agent = self.request.query_params.get('agent')

        if agent and strategy:
            reserve_wallet = get_object_or_404(
                ReserveWallet,
                request_id=f'strategy:{strategy}:{agent}'
            )

            orders = set(
                Order.objects.filter(
                    wallet__variant=reserve_wallet and reserve_wallet.group_id,
                    filled_amount__gt=Decimal('0')
                ).values_list('id', flat=True)
            )

            trades = trades.filter(order_id__in=orders)

        market = self.request.query_params.get('market')
        if market:
            trades = trades.filter(market=market)

        return trades.select_related('symbol', 'symbol__asset', 'symbol__base_asset').order_by('-created')


class TradeHistoryView(ListAPIView):
    permission_classes = ()
    pagination_class = FastLimitOffsetPagination
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]
    serializer_class = TradeSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Trade.objects.none()

        symbol = self.request.query_params.get('symbol')
        my = self.request.query_params.get('my')
        pair_symbol = get_object_or_404(PairSymbol, name=symbol, enable=True)

        user = self.request.user

        if my == '1':
            if not user.is_authenticated:
                return Trade.objects.none()

            return Trade.objects.filter(
                account=user.get_account(),
                symbol=pair_symbol
            ).order_by('-created')[:15]

        else:
            return Trade.objects.filter(
                is_maker=True,
                symbol=pair_symbol
            ).order_by('-created')[:15]

    def list(self, request, *args, **kwargs):
        serializer = TradeSerializer(self.get_queryset(), many=True)

        return Response({
            'results': serializer.data
        })


class TradePairsHistoryView(ListAPIView):
    authentication_classes = (CustomTokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    pagination_class = LimitOffsetPagination
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]
    serializer_class = TradePairSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Trade.objects.none()

        min_id = self.request.query_params.get('from_id')
        id_filter = {'id__gt': min_id} if min_id else {}
        filter_self = self.request.query_params.get('self', False)

        qs = Trade.objects.filter(
            **id_filter
        )
        if filter_self:
            account_id = self.request.user.account.id

            group_ids = set(qs.values('group_id').annotate(
                maker_account_id=Min('account_id'),
                taker_account_id=Max('account_id'),
            ).exclude(
                maker_account_id=F('taker_account_id')
            ).filter(
                Q(maker_account_id=account_id) |
                Q(taker_account_id=account_id)
            ).values_list('group_id', flat=True))
            qs = qs.filter(group_id__in=group_ids)

        return qs.filter(account=self.request.user.account).prefetch_related('symbol').order_by('id')

    def list(self, request, *args, **kwargs):
        min_id = self.request.query_params.get('from_id')
        filter_self = self.request.query_params.get('self', False)

        id_filter = {'id__gt': min_id} if min_id else {}
        qs = self.get_queryset()

        mapping_qs = Trade.objects.filter(group_id__in=qs.values_list('group_id', flat=True), **id_filter).values(
            'group_id').annotate(
            maker_order_id=Min('order_id'), taker_order_id=Max('order_id'),
            maker_account_id=Min('account_id'), taker_account_id=Max('account_id')
        )

        if filter_self:
            mapping_qs = mapping_qs.exclude(maker_account_id=F('taker_account_id'))

        maker_taker_mapping = {t['group_id']: (t['maker_order_id'], t['taker_order_id']) for t in mapping_qs}

        all_order_ids = set(sum(maker_taker_mapping.values(), ()))
        client_order_id_mapping = {o.id: o.client_order_id for o in Order.objects.filter(id__in=all_order_ids)}
        serializer = TradePairSerializer(qs, context={
            'maker_taker_mapping': maker_taker_mapping,
            'client_order_id_mapping': client_order_id_mapping,
        }, many=True)

        return Response({
            'results': serializer.data
        })
