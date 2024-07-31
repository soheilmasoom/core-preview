import django_filters

from ledger.models import OTCTrade, OTCRequest
from market.serializers.trade_serializer import AccountTradeSerializer
from market.views import AccountTradeHistoryView
from rest_framework import serializers
from django.db.models import Q


class OTCFilter(django_filters.FilterSet):
    coin = django_filters.CharFilter(field_name='symbol__asset__symbol', lookup_expr='iexact')
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte')
    created = django_filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = OTCRequest
        fields = ('coin', 'side', 'created_after', 'type')


class OTCRequestSerializer(AccountTradeSerializer):
    from_asset = serializers.CharField(source='from_asset.symbol')
    to_asset = serializers.CharField(source='to_asset.symbol')
    otc_trade_status = serializers.CharField(source='otctrade.status')

    class Meta(AccountTradeSerializer.Meta):
        model = OTCRequest
        fields = (*AccountTradeSerializer.Meta.fields, 'from_asset', 'to_asset', 'from_amount', 'to_amount', 'otc_trade_status', 'otctrade', 'type', 'gtd', 'trigger_price')
        ref_name = 'OTCHistoryRequestSerializer'  # Unique name


class OTCHistoryView(AccountTradeHistoryView):
    filter_class = OTCFilter
    serializer_class = OTCRequestSerializer

    def get_queryset(self):

        if getattr(self, 'swagger_fake_view', False):
            return OTCRequest.objects.none()

        return OTCRequest.objects.filter(
            ~Q(otctrade=None),
            otctrade__status__in=[OTCTrade.DONE, OTCTrade.PENDING, OTCTrade.USER_CANCELED, OTCTrade.EXPIRED],
            account=self.request.user.get_account(),
        ).select_related('symbol', 'symbol__asset', 'symbol__base_asset').order_by('-created')
