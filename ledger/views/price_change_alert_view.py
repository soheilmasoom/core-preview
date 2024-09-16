from rest_framework import permissions
from rest_framework import serializers
from ledger.models.price_change_alert import PriceChangeAlert
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated

from ledger.tasks.alert import check_price_alerts


class PriceChangeAlertSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True)
    remaining_alerts = serializers.SerializerMethodField()

    class Meta:
        model = PriceChangeAlert
        fields = ['asset', 'base_asset', 'trigger_price', 'type', 'description', 'remaining_alerts']

    def get_remaining_alerts(self, obj):
        user = obj.user
        asset = obj.asset
        active_alerts_count = PriceChangeAlert.objects.filter(user=user, asset=asset, active=True).count()
        return max(0, 10 - active_alerts_count)


class PriceChangeAlertView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        alerts = PriceChangeAlert.objects.filter(user=request.user)
        serializer = PriceChangeAlertSerializer(alerts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):

        user = request.user
        asset_id = request.data.get('asset')
        active_alerts_count = PriceChangeAlert.objects.filter(user=user, asset_id=asset_id, active=True).count()

        if active_alerts_count >= 10:
            remaining_alerts = max(0, 10 - active_alerts_count)
            return Response({'detail': 'حداکثر ۱۰ هشدار برای هر ارز دیجیتال مجاز است.', 'remaining_alerts': remaining_alerts}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PriceChangeAlertSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=user)
            remaining_alerts = max(0, 10 - PriceChangeAlert.objects.filter(user=user, asset_id=asset_id, active=True).count())
            response_data = serializer.data
            response_data['remaining_alerts'] = remaining_alerts
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        alert = get_object_or_404(PriceChangeAlert, pk=pk, user=request.user)
        alert.delete()
        active_alerts_count = PriceChangeAlert.objects.filter(user=request.user, asset=alert.asset, active=True).count()
        remaining_alerts = max(0, 10 - active_alerts_count)

        return Response({'detail': 'Alert deleted successfully.', 'remaining_alerts': remaining_alerts}, status=status.HTTP_204_NO_CONTENT)