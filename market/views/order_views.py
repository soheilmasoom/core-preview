import logging
from datetime import datetime

import django_filters
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import CreateAPIView, get_object_or_404
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from accounts.authentication import CustomJWTAuthentication, TradeTokenAuthentication, CustomTokenAuthentication
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from accounts.views.jwt_views import DelegatedAccountMixin, user_has_delegate_permission
from ledger.models.wallet import ReserveWallet
from market.models import Order, CancelRequest, PairSymbol, OCO
from market.models import StopLoss, Trade
from market.serializers.cancel_request_serializer import CancelRequestSerializer, BulkCancelRequestSerializer
from market.serializers.oco_serializer import OCOSerializer
from market.serializers.order_serializer import OrderIDSerializer, OrderSerializer
from market.serializers.order_stoploss_serializer import OrderStopLossSerializer
from market.serializers.stop_loss_serializer import StopLossSerializer

logger = logging.getLogger(__name__)

class OrderFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name='symbol__name', lookup_expr='iexact')
    market = django_filters.CharFilter(field_name='wallet__market')
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte')
    created = django_filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = Order
        fields = ('symbol', 'status', 'market', 'side', 'client_order_id', 'created_after')


class StopLossFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name='symbol__name')
    market = django_filters.CharFilter(field_name='wallet__market')

    class Meta:
        model = StopLoss
        fields = ('symbol', 'market')


class OrderViewSet(mixins.CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   mixins.ListModelMixin,
                   GenericViewSet,
                   DelegatedAccountMixin):
    authentication_classes = (SessionAuthentication, TradeTokenAuthentication, CustomJWTAuthentication)
    pagination_class = LimitOffsetPagination
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    filter_backends = [DjangoFilterBackend]
    filter_class = OrderFilter

    def get_serializer_class(self):
        if self.request.query_params.get('only_id') == '1':
            return OrderIDSerializer
        else:
            return OrderSerializer

    def get_queryset(self):
        account, variant = self.get_account_variant(self.request)

        filters = {}
        if variant:
            filters = {'wallet__variant': variant}
        elif self.request.query_params.get('agent') and self.request.query_params.get('strategy'):
            reserve_wallet = ReserveWallet.objects.filter(
                request_id=f'strategy:{self.request.query_params.get("strategy")}:{self.request.query_params.get("agent")}'
            ).first()
            if reserve_wallet:
                filters = {'wallet__variant': reserve_wallet.group_id}
            else:
                return Order.objects.none()

        return Order.objects.filter(account=account, **filters).select_related(
            'symbol', 'wallet', 'stop_loss').order_by('-created')

    def get_serializer_context(self):
        account, variant = self.get_account_variant(self.request)
        context = {
            **super(OrderViewSet, self).get_serializer_context(),
            'account': account,
            'variant': variant,
        }
        if self.request.query_params.get('only_id') == '1' or self.request.method != 'GET':
            return context
        else:
            order_filter = {}
            client_order_id = self.request.query_params.get('client_order_id')
            order_id = self.request.query_params.get('id')
            if client_order_id:
                order_filter = {'client_order_id': client_order_id}
            elif order_id:
                order_filter = {'id': order_id}
            context['trades'] = Trade.get_account_orders_filled_price(account, order_filter)
            return context


class OpenOrderListAPIView(APIView):
    authentication_classes = (SessionAuthentication, CustomTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def get(self, request, *args, **kwargs):
        account = self.request.user.get_account()

        filters = {}
        exclude_filters = {}
        symbol_filter = self.request.query_params.get('symbol')
        side_filter = self.request.query_params.get('side')
        bot_filter = self.request.query_params.get('bot')
        oco_filter = self.request.query_params.get('oco')
        if symbol_filter:
            symbol = get_object_or_404(PairSymbol, name=symbol_filter.upper(), enable=True)
            filters['symbol'] = symbol
        if side_filter:
            filters['side'] = side_filter
        if oco_filter:
            filters['oco__isnull'] = not (str(oco_filter) == '1')
        if bot_filter:
            reserved_variants = ReserveWallet.objects.filter(sender__account=account).values_list('group_id', flat=True)
            if str(bot_filter) == '1':
                filters['wallet__variant__in'] = reserved_variants
            else:
                exclude_filters['wallet__variant__in'] = reserved_variants

        open_orders = Order.open_objects.filter(
            account=account, stop_loss__isnull=True, **filters
        ).exclude(**exclude_filters).select_related('symbol', 'wallet', )

        open_stop_losses = StopLoss.open_objects.filter(
            wallet__account=account, **filters
        ).exclude(**exclude_filters).select_related('symbol', 'wallet')

        order_filter = {
            'id__in': list(open_orders.values_list('id', flat=True)) + list(
                open_stop_losses.exclude(order__isnull=True).values_list('order', flat=True))
        }
        context = {
            'trades': Trade.get_account_orders_filled_price(account, order_filter=order_filter),
        }

        serialized_orders = OrderStopLossSerializer(open_orders, many=True, context=context)
        serialized_stop_losses = OrderStopLossSerializer(open_stop_losses, many=True, context=context)

        date_pattern = '%Y-%m-%dT%H:%M:%S.%f%z'

        sorted_results = sorted(
            (serialized_orders.data + serialized_stop_losses.data),
            key=lambda obj: datetime.strptime(obj['created'], date_pattern), reverse=True
        )
        return Response(sorted_results)


class CancelOrderAPIView(CreateAPIView, DelegatedAccountMixin):
    authentication_classes = (SessionAuthentication, TradeTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    serializer_class = CancelRequestSerializer
    queryset = CancelRequest.objects.all()

    def get_serializer_context(self):
        return {
            **super(CancelOrderAPIView, self).get_serializer_context(),
            'account': self.get_account_variant(self.request)[0],
            'allow_cancel_strategy_orders': user_has_delegate_permission(self.request.user)
        }


class BulkCancelOrderAPIView(APIView):
    authentication_classes = (SessionAuthentication, TradeTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def post(self, request):
        serializer = BulkCancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_ids = serializer.data.get('id_list')
        client_order_id_list = serializer.data.get('client_order_id_list')

        q = Q()
        if order_ids:
            q = q | Q(id__in=order_ids)

        if client_order_id_list:
            q = q | Q(client_order_id__in=client_order_id_list)

        try:
            if q:
                to_cancel_orders = Order.open_objects.filter(q, account=request.user.get_account())
                Order.bulk_cancel_simple_orders(to_cancel_orders=to_cancel_orders)
        except Exception as e:
            logger.exception(f'failed bulk cancel order due to {e}', extra={
                'e': e
            })
            return Response({"Error": 'خطایی رخ داد.'}, 400)

        return Response({'status': 'done'}, status=200)


class StopLossViewSet(ModelViewSet, DelegatedAccountMixin):
    permission_classes = (IsAuthenticated,)
    pagination_class = LimitOffsetPagination

    serializer_class = StopLossSerializer

    filter_backends = [DjangoFilterBackend]
    filter_class = StopLossFilter

    def get_queryset(self):
        return StopLoss.objects.filter(wallet__account=self.get_account_variant(self.request)[0]).order_by('-created')

    def get_serializer_context(self):
        account, variant = self.get_account_variant(self.request)
        return {
            **super(StopLossViewSet, self).get_serializer_context(),
            'account': account,
            'variant': variant,
        }


class OCOViewSet(ModelViewSet, DelegatedAccountMixin):
    permission_classes = (IsAuthenticated,)
    pagination_class = LimitOffsetPagination

    serializer_class = OCOSerializer

    filter_backends = [DjangoFilterBackend]
    # filter_class = StopLossFilter

    def get_queryset(self):
        return OCO.objects.filter(wallet__account=self.get_account_variant(self.request)[0]).order_by('-created')

    def get_serializer_context(self):
        account, variant = self.get_account_variant(self.request)
        return {
            **super(OCOViewSet, self).get_serializer_context(),
            'account': account,
            'variant': variant,
        }
