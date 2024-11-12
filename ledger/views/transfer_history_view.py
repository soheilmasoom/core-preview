from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination

from accounts.authentication import CustomJWTAuthentication, CustomTokenAuthentication
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from ledger.fields import WithdrawSources
from ledger.models import Transfer
from ledger.models.asset import AssetSerializerMini
from ledger.utils.fields import INIT, PROCESS, REFUND, DONE, CANCELED
from ledger.utils.precision import get_presentation_amount


class TransferSerializer(serializers.ModelSerializer):
    link = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    fee_amount = serializers.SerializerMethodField()
    network = serializers.SerializerMethodField()
    min_confirm = serializers.SerializerMethodField()
    unlock_confirm = serializers.SerializerMethodField()
    confirmation = serializers.SerializerMethodField()
    asset = AssetSerializerMini(source='wallet.asset', read_only=True)
    is_internal = serializers.SerializerMethodField()
    cancelable = serializers.SerializerMethodField()

    def get_network(self, transfer: Transfer):
        return transfer.network and transfer.network.symbol

    def get_min_confirm(self, transfer: Transfer):
        return transfer.network.min_confirm if transfer.network else None

    def get_unlock_confirm(self, transfer: Transfer):
        return transfer.network.unlock_confirm if transfer.network else None

    def get_link(self, transfer: Transfer):
        return transfer.get_explorer_link()

    def get_amount(self, transfer: Transfer):
        return get_presentation_amount(transfer.amount)

    def get_fee_amount(self, transfer: Transfer):
        return get_presentation_amount(transfer.fee_amount)

    def get_is_internal(self, transfer: Transfer):
        return transfer.source in [WithdrawSources.INTERNAL, WithdrawSources.INTERNAL_ACCOUNT]

    def get_confirmation(self, transfer: Transfer):
        if not transfer.network:
            return 0
        if transfer.status == DONE:
            return transfer.network.min_confirm

        return transfer.get_confirmation_blocks() or 0

    def get_cancelable(self, transfer: Transfer):
        return \
            transfer.status == INIT or \
            (transfer.status == PROCESS and transfer.in_freeze_time())

    class Meta:
        model = Transfer
        fields = ('id', 'created', 'amount', 'status', 'link', 'out_address', 'asset', 'network', 'trx_hash',
                  'fee_amount', 'is_internal', 'cancelable', 'min_confirm', 'unlock_confirm', 'confirmation')


class WithdrawHistoryView(ListAPIView):
    authentication_classes = (SessionAuthentication, CustomTokenAuthentication, CustomJWTAuthentication)

    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    serializer_class = TransferSerializer
    pagination_class = LimitOffsetPagination

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status']

    def get_queryset(self):
        query_params = self.request.query_params

        queryset = Transfer.objects.filter(
            wallet__account=self.request.user.get_account(),
            deposit=False,
        ).exclude(
            status=REFUND
        ).order_by('-created')

        if 'coin' in query_params:
            queryset = queryset.filter(wallet__asset__symbol=query_params['coin'])

        return queryset.prefetch_related('network')


class DepositHistoryView(WithdrawHistoryView):
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def get_queryset(self):
        query_params = self.request.query_params

        queryset = Transfer.objects.filter(
            wallet__account=self.request.user.get_account(),
            deposit=True,
        ).exclude(
            status__in=[CANCELED, REFUND]
        ).order_by('-created')

        if 'coin' in query_params:
            queryset = queryset.filter(wallet__asset__symbol=query_params['coin'])

        return queryset.prefetch_related('network')
