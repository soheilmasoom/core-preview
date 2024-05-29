from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination

from ledger.models import NetworkAsset
from ledger.models.asset import AssetSerializerMini
from ledger.utils.precision import get_presentation_amount


class NetworkAssetSerializer(serializers.ModelSerializer):
    asset = AssetSerializerMini()
    network = serializers.CharField(source='network.symbol')
    network_name = serializers.CharField(source='network.name')
    slow_withdraw = serializers.SerializerMethodField()

    withdraw_commission = serializers.SerializerMethodField()
    min_withdraw = serializers.SerializerMethodField()
    min_deposit = serializers.SerializerMethodField()

    def get_min_withdraw(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.withdraw_min)

    def get_withdraw_commission(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.withdraw_fee)

    def get_min_deposit(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.get_min_deposit())

    def get_slow_withdraw(self, network_asset: NetworkAsset):
        return not network_asset.network.can_withdraw

    class Meta:
        fields = ('asset', 'network', 'network_name', 'withdraw_commission', 'min_withdraw', 'min_deposit',
                  'slow_withdraw')
        model = NetworkAsset


class NetworkAssetView(ListAPIView):
    permission_classes = []
    pagination_class = LimitOffsetPagination
    search_fields = ['asset__symbol', 'asset__name', 'asset__name_fa', 'network__symbol', 'network__name']
    serializer_class = NetworkAssetSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]

    queryset = NetworkAsset.objects.filter(
        Q(can_deposit=True, network__can_deposit=True) | Q(network__can_withdraw=True, can_withdraw=True),
        asset__enable=True,
    ).order_by('-asset__pin_to_top', '-asset__trend', 'asset__order', 'withdraw_fee').distinct()
