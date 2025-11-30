from django.db import models

from ledger.utils.fields import get_amount_field


class BlocklinkIncome(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    start = models.DateTimeField()
    network = models.CharField(max_length=16)
    coin = models.CharField(max_length=16)

    real_fee_amount = get_amount_field()
    fee_cost = get_amount_field()
    fee_income = get_amount_field()

    class Meta:
        unique_together = ('coin', 'network', 'start')
