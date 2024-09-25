from django.db import models
from ledger.models.asset_alert import AssetAlert

from ledger.utils.fields import get_amount_field

PRICE_CHANGE_ALERT_TYPES = [
    ("gt", "Greater Than"),
    ("gte", "Greater Than or Equal To"),
    ("lt", "Less Than"),
    ("lte", "Less Than or Equal To"),
]


class AssetAlertRule(models.Model):
    MAX_ALERT_RULE_COUNT = 10

    asset_alert = models.ForeignKey(to='AssetAlert', on_delete=models.CASCADE)
    is_triggered = models.BooleanField(default=False)
    trigger_price = get_amount_field()
    active = models.BooleanField(default=True)
    type = models.CharField(max_length=8, choices=PRICE_CHANGE_ALERT_TYPES)
    description = models.TextField(verbose_name='توضیحات', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.asset_alert.user.username} - {self.asset_alert.asset.symbol} at {self.trigger_price}'

    @classmethod
    def get_active_alert_rule_count(cls, user, asset_id):
        return cls.objects.filter(asset_alert__user=user, asset_alert__asset_id=asset_id, active=True).count()

    @classmethod
    def get_remaining_alert_rule_count(cls, user, asset_id):
        return max(0, cls.MAX_ALERT_RULE_COUNT - cls.get_active_alert_rule_count(user, asset_id))