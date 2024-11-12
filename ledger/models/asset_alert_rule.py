from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone
from simple_history.models import HistoricalRecords

from accounts.models import Notification
from ledger.models import Asset
from ledger.utils.fields import get_amount_field
from ledger.utils.precision import get_presentation_amount
from ledger.utils.price import get_last_price
from ledger.utils.wallet_pipeline import DECIMAL


class AssetAlertRule(models.Model):
    history = HistoricalRecords()

    MAX_RULES_PER_ASSET_ALERT = 10

    USER, TRIGGER = 'user', 'trigger'

    TYPES = LTE, GTE = 'lt', 'gt'
    TYPES_CHOICES = [(LTE, 'کمتر از'), (GTE, 'بیشتر از')]
    TYPES_DIRECTION_VERBOSE = {
        GTE: 'افزایش',
        LTE: 'کاهش'
    }

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    asset_alert = models.ForeignKey(to='AssetAlert', on_delete=models.CASCADE, related_name='rules')

    base_asset = models.ForeignKey(
        to='Asset',
        on_delete=models.CASCADE,
        related_name='base_asset_alert_rules',
        limit_choices_to={'symbol__in': [Asset.IRT, Asset.USDT]}
    )

    trigger_price = get_amount_field()
    active = models.BooleanField(default=True)
    type = models.CharField(max_length=8, choices=TYPES_CHOICES)
    description = models.TextField(verbose_name='توضیحات', blank=True)

    current_state = models.CharField(max_length=8, choices=TYPES_CHOICES, blank=True)
    last_trigger_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.asset_alert.user.username} - {self.asset_alert.asset}-{self.base_asset} on ' \
               f'{self.type} {get_presentation_amount(self.trigger_price)}'
    
    class Meta:
        ordering = ('id', )

    def get_state(self, price: Decimal) -> str:
        if price > self.trigger_price:
            return self.GTE
        elif price < self.trigger_price:
            return self.LTE
        else:
            return self.type

    def reset_state(self):
        self.current_state = ''
        self.save(update_fields=['current_state'])

    def update_current_price(self, price: Decimal = None) -> bool:
        if not price:
            price = get_last_price(f'{self.asset_alert.asset.symbol}{self.base_asset.symbol}')

            if not price:
                return False

        new_state = self.get_state(price)

        if not self.current_state:
            self.current_state = new_state
            self.save(update_fields=['current_state'])
            return False

        if new_state == self.current_state:
            return False

        trigger_alert = new_state == self.type

        with transaction.atomic():
            to_update = ['current_state']

            if trigger_alert:  # trigger condition
                self.last_trigger_time = timezone.now()
                self.active = False
                to_update.extend(['last_trigger_time', 'active'])

                asset = self.asset_alert.asset

                title = f'{AssetAlertRule.TYPES_DIRECTION_VERBOSE[self.type]} {asset.name_fa}'

                presentation_price = get_presentation_amount(self.trigger_price, precision=DECIMAL)

                if new_state == AssetAlertRule.GTE:
                    message = f'قیمت {asset.name_fa}، {presentation_price} {self.base_asset.name_fa} را رد کرد'
                else:
                    message = f'قیمت {asset.name_fa} به زیر {presentation_price} {self.base_asset.name_fa} رسید'

                Notification.send(
                    recipient=self.asset_alert.user,
                    title=title,
                    message=message,
                    link=f'/price/{asset.name}',
                    # hidden=True
                )

            self.current_state = new_state
            self.save(update_fields=to_update)

        return trigger_alert
