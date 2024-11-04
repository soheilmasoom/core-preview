from django.db import models

from accounts.models import User
from ledger.models import Asset, CoinCategory
from ledger.models.asset_alert_rule import AssetAlertRule
from ledger.utils.fields import get_amount_field


class LiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(active=True)


class AlertTrigger(models.Model):
    FIVE_MIN = '5m'
    ONE_HOUR = '1h'
    THREE_HOURS = '3h'
    SIX_HOURS = '6h'
    TWELVE_HOURS = '12h'
    ONE_DAY = '24h'

    INTERVAL_CHOICES = [
        (FIVE_MIN, 'پنج‌ دقیقه'),
        (ONE_HOUR, '‌یک‌ ساعت'),
        (THREE_HOURS, 'سه ساعت'),
        (SIX_HOURS, 'شش ساعت'),
        (TWELVE_HOURS, 'دوازده ساعت'),
        (ONE_DAY, 'یک روز')
    ]

    INTERVAL_MINUTES_MAPPING = {
        FIVE_MIN: 5,
        ONE_HOUR: 60,
        THREE_HOURS: 3 * 60,
        SIX_HOURS: 6 * 60,
        TWELVE_HOURS: 12 * 60,
        ONE_DAY: 24 * 60
    }

    INTERVAL_VERBOSE_MAP = dict(INTERVAL_CHOICES)

    TRIGGERS = TRIGGER_PRICE_RATIO, TRIGGER_CHANNEL_CHANGE = 'ratio', 'channel'

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    trigger_type = models.CharField(max_length=8, choices=[(t, t) for t in TRIGGERS], db_index=True)
    old_price = get_amount_field()
    new_price = get_amount_field()
    cycle = models.PositiveIntegerField()
    interval = models.CharField(choices=INTERVAL_CHOICES, max_length=15)
    fcm_key = models.CharField(max_length=256, blank=True)


class AssetAlert(models.Model):
    MAX_ASSET_ALERTS_PER_USER = 1000

    objects = models.Manager()
    live_objects = LiveManager()

    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='asset_alerts')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    active = models.BooleanField(default=False, db_index=True)

    @classmethod
    def get_default_rule_push_topic(cls, asset: Asset):
        return f'price_alerts_{asset.symbol.lower()}'

    def get_rules_count(self):
        return AssetAlertRule.objects.filter(active=True).count()

    def activate(self):
        from accounts.utils.price_alert import subscribe_alert

        self.active = True
        subscribe_alert(self)
        self.save(update_fields=['active'])

    def deactivate(self):
        from accounts.utils.price_alert import unsubscribe_alert

        self.active = False
        unsubscribe_alert(self)
        self.save(update_fields=['active'])

    class Meta:
        unique_together = [('user', 'asset')]


class BulkAssetAlert(models.Model):
    CATEGORY_MY_ASSETS = 'my_assets'
    CATEGORY_ALL_COINS = 'all_coins'
    CATEGORY_COIN_CATEGORIES = 'coin_categories'

    CATEGORIES = [
        (CATEGORY_MY_ASSETS, CATEGORY_MY_ASSETS),
        (CATEGORY_ALL_COINS, CATEGORY_ALL_COINS),
        (CATEGORY_COIN_CATEGORIES, CATEGORY_COIN_CATEGORIES),
    ]

    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subscription_type = models.CharField(choices=CATEGORIES, max_length=20)
    coin_category = models.ForeignKey(CoinCategory, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = [('user', 'subscription_type', 'coin_category')]
