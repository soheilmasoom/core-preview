from django.db import models
from ledger.utils.fields import get_amount_field

PRICE_CHANGE_ALERT_TYPES = [
    ("gt", "Greater Than"),
    ("lt", "Less Than"),
]

class AssetAlertRule(models.Model):
    MAX_ALERT_RULE_COUNT = 10
    USER, TRIGGER = 'user', 'trigger'

    ALERT_DEACTIVE_REASON_CHOICES = [
        (USER, USER),
        (TRIGGER, TRIGGER),
    ]

    asset_alert = models.ForeignKey(to='AssetAlert', on_delete=models.CASCADE)
    base_asset = models.ForeignKey('Asset', on_delete=models.CASCADE, related_name='asset_alert_rule_base_asset')
    is_triggered = models.BooleanField(default=False)
    trigger_price = get_amount_field()
    active = models.BooleanField(default=True)
    type = models.CharField(max_length=8, choices=PRICE_CHANGE_ALERT_TYPES)
    description = models.TextField(verbose_name='توضیحات', blank=True)
    created = models.DateTimeField(auto_now_add=True)
    deactive_reason = models.CharField(max_length=8, choices=ALERT_DEACTIVE_REASON_CHOICES, blank=True)

    def __str__(self):
        return f'{self.asset_alert.user.username} - {self.asset_alert.asset.symbol}-{self.asset_alert.base_asset.symbol} at {self.trigger_price}'

    @classmethod
    def get_active_alert_rule_count(cls, user, asset_alert_id):
        return cls.objects.filter(asset_alert__user=user, asset_alert_id=asset_alert_id, active=True).count()

    @classmethod
    def get_remaining_alert_rule_count(cls, user, asset_alert_id):
        return max(0, cls.MAX_ALERT_RULE_COUNT - cls.get_active_alert_rule_count(user, asset_alert_id))
