from django.core.exceptions import ValidationError
from django.db import models

from ledger.utils.external_price import BUY
from ledger.utils.fields import get_group_id_field, get_amount_field, get_status_field
from ledger.utils.price import get_last_price, USDT_IRT
from market.models import BaseTrade


class ManualTrade(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    group_id = get_group_id_field()

    account = models.ForeignKey('accounts.Account', on_delete=models.CASCADE, null=True, blank=True)

    side = models.CharField(max_length=8, choices=BaseTrade.SIDE_CHOICES, default=BUY)
    amount = get_amount_field()
    price = get_amount_field()
    filled_price = get_amount_field()

    status = get_status_field()

    def clean(self):
        current_price = get_last_price(USDT_IRT) or 0

        if abs(self.price / current_price - 1) > 0.1:
            raise ValidationError('Invalid price! current is %s' % current_price)
