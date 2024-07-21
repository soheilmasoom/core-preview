import django_filters
from django.db.models import Q

from ledger.models import OTCRequest, OTCTrade
from market.serializers.trade_serializer import AccountTradeSerializer
from market.views import AccountTradeHistoryView

from rest_framework import serializers

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