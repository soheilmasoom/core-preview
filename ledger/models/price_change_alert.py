from django.db import models

from ledger.utils.fields import get_amount_field

PRICE_CHANGE_ALERT_TYPES = [
    ("gt", "Greater Than"),
    ("gte", "Greater Than or Equal To"),
    ("lt", "Less Than"),
    ("lte", "Less Than or Equal To"),
]

class PriceChangeAlert(models.Model):
    user = models.ForeignKey(to='accounts.User', on_delete=models.CASCADE)
    asset = models.ForeignKey(to='ledger.Asset', on_delete=models.CASCADE)
    base_asset = models.ForeignKey(to='ledger.Asset', on_delete=models.CASCADE, related_name="price_change_base_asset")
    is_triggered = models.BooleanField(default=False)
    trigger_price = get_amount_field()
    active = models.BooleanField(default=True)
    type = models.CharField(max_length=8, choices=PRICE_CHANGE_ALERT_TYPES)
    description = models.TextField(verbose_name='توضیحات', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} - {self.asset.symbol}{self.base_asset.symbol} at ${self.trigger_price}'
