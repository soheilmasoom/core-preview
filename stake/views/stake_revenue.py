from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers

from rest_framework.generics import ListAPIView

from ledger.utils.precision import get_presentation_amount
from stake.models import StakeRevenue
from stake.views.stake_request_view import StakeRequestSerializer


class StakeRevenueSerializer(serializers.ModelSerializer):
    stake_request = StakeRequestSerializer()

    revenue = serializers.SerializerMethodField()

    def get_revenue(self, stake_revenue: StakeRevenue):
        return get_presentation_amount(stake_revenue.revenue)

    class Meta:
        model = StakeRevenue
        fields = ('created', 'stake_request', 'revenue')


class StakeRevenueAPIView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['stake_request']

    serializer_class = StakeRevenueSerializer

    def get_queryset(self):
        return StakeRevenue.objects.filter(stake_request__account=self.request.user.get_account()).order_by('-created')
