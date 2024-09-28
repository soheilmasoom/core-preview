from rest_framework import permissions
from rest_framework import serializers
from ledger.models.asset_alert import AssetAlert
from ledger.models.asset_alert_rule import AssetAlertRule
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets


class AssetAlertRuleSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False)
    remaining_alerts = serializers.SerializerMethodField()

    class Meta:
        model = AssetAlertRule
        fields = ['id', 'trigger_price', 'type', 'description', 'remaining_alerts']

    def get_remaining_alerts(self, obj):
        user = obj.asset_alert.user
        asset = obj.asset_alert.asset
        return AssetAlertRule.get_remaining_alert_rule_count(user=user, asset_id=asset.id)


class AssetAlertRuleViewSet(viewsets.ModelViewSet):
    serializer_class = AssetAlertRuleSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return AssetAlertRule.objects.filter(asset_alert__user=self.request.user, asset_alert__asset__id=self.kwargs['asset_pk'])

    def create(self, request, *args, **kwargs):
        user = request.user
        asset_id = self.kwargs['asset_pk']
        asset_alert = get_object_or_404(AssetAlert, user=user, asset_id=asset_id)

        active_alerts_count = AssetAlertRule.get_active_alert_rule_count(user=user, asset_id=asset_id)

        if active_alerts_count >= AssetAlertRule.MAX_ALERT_RULE_COUNT:
            remaining_alerts = AssetAlertRule.get_remaining_alert_rule_count(user, asset_id)
            return Response({'detail': f'حداکثر {AssetAlertRule.MAX_ALERT_RULE_COUNT} هشدار برای هر ارز دیجیتال مجاز است.', 'remaining_alerts': remaining_alerts}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(asset_alert=asset_alert)
            remaining_alerts = AssetAlertRule.get_remaining_alert_rule_count(user=user, asset_id=asset_id)
            response_data = serializer.data
            response_data['remaining_alerts'] = remaining_alerts
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_object(self):
        alert_rule = get_object_or_404(AssetAlertRule, pk=self.kwargs['rule_pk'], asset_alert__user=self.request.user)
        return alert_rule

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'detail': 'هشدار قمیت حذف شد.'}, status=status.HTTP_204_NO_CONTENT)
