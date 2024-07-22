import logging
import django_filters
from django.db.models import Q

from ledger.models import OTCRequest, OTCTrade
from market.serializers.trade_serializer import AccountTradeSerializer
from market.views import AccountTradeHistoryView

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework import serializers
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from accounts.authentication import TradeTokenAuthentication

logger = logging.getLogger(__name__)

class LimitOTCFilter(django_filters.FilterSet):
    coin = django_filters.CharFilter(field_name='symbol__asset__symbol', lookup_expr='iexact')
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte')
    created = django_filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = OTCRequest
        fields = ('coin', 'side', 'created_after')


class LimitOTCRequestSerializer(AccountTradeSerializer):
    from_asset = serializers.CharField(source='from_asset.symbol')
    to_asset = serializers.CharField(source='to_asset.symbol')
    otc_trade_status = serializers.CharField(source='otctrade.status')

    class Meta(AccountTradeSerializer.Meta):
        model = OTCRequest
        fields = (*AccountTradeSerializer.Meta.fields, 'from_asset', 'to_asset', 'otc_trade_status', 'otctrade', 'type', 'gtd', 'trigger_price')
        ref_name = 'LimitOTCRequestSerializer'

class LimitOTCView(AccountTradeHistoryView):
    filter_class = LimitOTCFilter
    serializer_class = LimitOTCRequestSerializer

    def get_queryset(self):

        if getattr(self, 'swagger_fake_view', False):
            return OTCRequest.objects.none()

        return OTCRequest.objects.filter(
            ~Q(otctrade=None),
            type=OTCRequest.LIMIT,
            account=self.request.user.get_account(),
        ).select_related('symbol', 'symbol__asset', 'symbol__base_asset').order_by('-created')


class CancelLimitOTCView(APIView):
    authentication_classes = (SessionAuthentication, TradeTokenAuthentication, JWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def post(self, request):
        serializer = CancelLimitOTCSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_ids = serializer.data.get('id_list')

        q = Q()
        if cancel_ids:
            q = q | Q(id__in=cancel_ids)

        try:
            cancel_otcs = list(OTCTrade.get_untriggered_otc_trade_queryset().filter(q))
            if cancel_otcs:
                for otc_trade in cancel_otcs:
                    otc_trade.cancel()
            else:
                return Response({"message": 'not found'}, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f'failed cancel limit otc due to {e}', extra={
                'e': e
            })
            return Response({"message": 'failed'}, status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'done'}, status=status.HTTP_200_OK)

class CancelLimitOTCSerializer(serializers.Serializer):
    id_list = serializers.ListField(
        child=serializers.IntegerField(min_value=0)
    )