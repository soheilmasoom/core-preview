import django_filters
from rest_framework import serializers

from ledger.models import TransactionHistory
from market.serializers.trade_serializer import AccountTradeSerializer
from market.views import AccountTradeHistoryView


class TransactionHistoryFilter(django_filters.FilterSet):
    created = django_filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = TransactionHistory
        fields = ('coin', 'type', 'created', 'group_id', 'status')


class TransactionHistorySerializer(serializers.ModelSerializer):
    class Meta(AccountTradeSerializer.Meta):
        model = TransactionHistory
        fields = ('created', 'group_id', 'status', 'type', 'amount', 'coin')


class TransactionHistoryView(AccountTradeHistoryView):
    filter_class = TransactionHistoryFilter
    serializer_class = TransactionHistorySerializer

    def get_queryset(self):
        return TransactionHistory.objects.filter(
            user=self.request.user
        )
