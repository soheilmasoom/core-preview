from django.db import models

from ledger.utils.fields import get_amount_field


class ManualWithdraw(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    receiver_address = models.CharField(max_length=256)
    network = models.ForeignKey('ledger.Network', on_delete=models.CASCADE)
    coin = models.CharField(max_length=16, db_index=True)
    amount = get_amount_field()
    memo = models.CharField(max_length=256, blank=True)
    comment = models.CharField(max_length=256, blank=True)

    triggered = models.BooleanField(default=False, db_index=True)
