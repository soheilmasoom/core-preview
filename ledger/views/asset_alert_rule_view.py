from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from ledger.models.asset import Asset, CoinField
from ledger.models.asset_alert import AssetAlert
from ledger.models.asset_alert_rule import AssetAlertRule
from ledger.utils.precision import get_presentation_amount


class AssetAlertRuleSerializer(serializers.ModelSerializer):
    base_asset = CoinField(coins=[Asset.IRT, Asset.USDT])

    class Meta:
        model = AssetAlertRule
        fields = ['id', 'trigger_price', 'type', 'base_asset']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['trigger_price'] = get_presentation_amount(instance.trigger_price)
        return representation

    def create(self, validated_data):
        asset_alert = validated_data['asset_alert']

        if asset_alert.get_rules_count() >= AssetAlertRule.MAX_RULES_PER_ASSET_ALERT:
            raise ValidationError(f'حداکثر {AssetAlertRule.MAX_RULES_PER_ASSET_ALERT} هشدار برای هر ارز دیجیتال مجاز است.')

        rule = super(AssetAlertRuleSerializer, self).create(validated_data)  # type: AssetAlertRule
        rule.update_current_price()

        return rule

    def update(self, rule: AssetAlertRule, validated_data):
        rule.reset_state()
        rule.update_current_price()
        return super(AssetAlertRuleSerializer, self).update(rule, validated_data)


class AssetAlertRuleViewSet(viewsets.ModelViewSet):
    serializer_class = AssetAlertRuleSerializer
    permission_classes = (IsAuthenticated,)

    def get_asset_alert(self) -> AssetAlert:
        coin = self.kwargs['coin']
        asset = get_object_or_404(Asset, enable=True, symbol=coin)
        alert, _ = AssetAlert.objects.get_or_create(asset=asset, user=self.request.user)
        return alert

    def get_queryset(self):
        return AssetAlertRule.objects.filter(
            asset_alert=self.get_asset_alert(),
            active=True
        )

    def list(self, request, *args, **kwargs):
        resp = super(AssetAlertRuleViewSet, self).list(request, *args, **kwargs)
        data = resp.data

        data.insert(0, {
            'id': 0,
            'trigger_price': 'instant',
            'type': 'default',
            'base_asset': Asset.IRT if self.kwargs['coin'] == Asset.USDT else Asset.USDT,
            'hint': 'در صورتی که قیمت بیش از 5 درصد به صورت ناگهانی یا 10 درصد در طول زمان تغییر کند، هشدار قیمت ارسال می‌شود.'
        })

        return resp

    def perform_create(self, serializer):
        serializer.save(asset_alert=self.get_asset_alert())

    def perform_update(self, serializer):
        serializer.save(asset_alert=self.get_asset_alert())

    def get_object(self):
        return get_object_or_404(
            AssetAlertRule,
            pk=self.kwargs['rule_pk'],
            asset_alert=self.get_asset_alert()
        )
