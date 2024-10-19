import django_filters
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.generics import ListAPIView, RetrieveAPIView, get_object_or_404
from rest_framework.pagination import LimitOffsetPagination

from financial.models import Payment, FiatWithdrawRequest
from financial.views.payment_view import PaymentHistorySerializer
from financial.views.withdraw_view import WithdrawHistorySerializer
from ledger.models import TransactionHistory, OTCTrade
from ledger.views.otc_history_view import OTCRequestSerializer


class TransactionHistoryFilter(django_filters.FilterSet):
    created = django_filters.IsoDateTimeFromToRangeFilter()
    type = django_filters.BaseInFilter()
    coin = django_filters.BaseInFilter()
    status = django_filters.BaseInFilter()

    class Meta:
        model = TransactionHistory
        fields = ('coin', 'type', 'created', 'group_id', 'status')


class TransactionHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionHistory
        fields = ('created', 'group_id', 'type', 'amount', 'coin', 'status', )


class TransactionHistoryView(ListAPIView):
    serializer_class = TransactionHistorySerializer
    pagination_class = LimitOffsetPagination

    filter_backends = [DjangoFilterBackend]
    filter_class = TransactionHistoryFilter

    def get_queryset(self):
        return TransactionHistory.objects.filter(
            user=self.request.user
        ).order_by('-created')


class TransactionDetailView(RetrieveAPIView):
    def get_object(self):
        user = self.request.user
        account = user.get_account()

        _type = self.kwargs['type']
        group_id = self.kwargs['group_id']

        if _type in ('buy', 'sell'):
            otc_trade = get_object_or_404(OTCTrade, group_id=group_id, otc_request__account=account)
            return otc_trade.otc_request
        elif _type == 'fiat_deposit':
            return get_object_or_404(Payment, group_id=group_id, user=user)
        elif _type == 'fiat_withdraw':
            return get_object_or_404(FiatWithdrawRequest, group_id=group_id, bank_account__user=user)
        else:
            raise Http404

    def get_serializer_class(self):
        _type = self.kwargs['type']

        if _type in ('buy', 'sell'):
            return OTCRequestSerializer
        elif _type == 'fiat_deposit':
            return PaymentHistorySerializer
        elif _type == 'fiat_withdraw':
            return WithdrawHistorySerializer
        else:
            raise Http404
