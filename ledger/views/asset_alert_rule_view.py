from rest_framework import permissions
from rest_framework import serializers
from ledger.models.asset import Asset
from ledger.models.asset_alert import AssetAlert
from ledger.models.asset_alert_rule import ALERT_DEACTIVE_REASON_CHOICES, AssetAlertRule
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets


class AlertRuleUpdateSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(required=True)

    class Meta:
        model = AssetAlertRule
        fields = ['active']

    def update(self, alert_rule, validated_data):
        is_active = validated_data.get('active')
        if is_active and not alert_rule.active:
            alert_rule.active = True
            alert_rule.is_triggered = False
            alert_rule.deactive_reason = None
        elif not is_active and alert_rule.active:
            alert_rule.active = False
            alert_rule.is_triggered = False
            alert_rule.deactive_reason = 'user'
        alert_rule.save(update_fields=['active', 'deactive_reason', 'is_triggered'])
        return alert_rule


class AssetAlertRuleSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False)
    remaining_alerts = serializers.SerializerMethodField()
    base_asset = serializers.CharField(required=True)

    class Meta:
        model = AssetAlertRule
        fields = ['id', 'trigger_price', 'type', 'description', 'remaining_alerts', 'base_asset', 'is_triggered', 'active']

    def get_remaining_alerts(self, obj):
        user = obj.asset_alert.user
        asset_alert_id = obj.asset_alert.id
        return AssetAlertRule.get_remaining_alert_rule_count(user, asset_alert_id)


class AssetAlertRuleViewSet(viewsets.ModelViewSet):
    serializer_class = AssetAlertRuleSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return AssetAlertRule.objects.filter(asset_alert__user=self.request.user, asset_alert__id=self.kwargs['asset_alert_pk'])

    def create(self, request, *args, **kwargs):
        user = request.user
        asset_alert_id = self.kwargs['asset_alert_pk']
        asset_alert = get_object_or_404(AssetAlert, user=user, pk=asset_alert_id)

        active_alerts_count = AssetAlertRule.get_active_alert_rule_count(user, asset_alert_id)
        if active_alerts_count >= AssetAlertRule.MAX_ALERT_RULE_COUNT:
            remaining_alerts = AssetAlertRule.get_remaining_alert_rule_count(user, asset_alert_id)
            return Response({'detail': f'حداکثر {AssetAlertRule.MAX_ALERT_RULE_COUNT} هشدار برای هر ارز دیجیتال مجاز است.', 'remaining_alerts': remaining_alerts}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            base_asset = serializer.validated_data['base_asset']
            base_asset = get_object_or_404(Asset, symbol=base_asset)
            serializer.save(asset_alert=asset_alert, base_asset=base_asset)
            remaining_alerts = AssetAlertRule.get_remaining_alert_rule_count(user, asset_alert_id)
            response_data = serializer.data
            response_data['remaining_alerts'] = remaining_alerts
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        alert_rule = self.get_object()
        serializer = AlertRuleUpdateSerializer(alert_rule, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            message = 'هشدار قیمت فعال شد.' if serializer.validated_data['active'] else 'هشدار قیمت غیرفعال شد.'
            return Response({'detail': message}, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_object(self):
        alert_rule = get_object_or_404(AssetAlertRule, pk=self.kwargs['rule_pk'], asset_alert_id=self.kwargs['asset_alert_pk'], asset_alert__user=self.request.user)
        return alert_rule

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'detail': 'هشدار قمیت حذف شد.'}, status=status.HTTP_204_NO_CONTENT)
