from django.db import models
from simple_history.models import HistoricalRecords

from ledger.utils.fields import get_amount_field


class BlocklinkDustCost(models.Model):
    history = HistoricalRecords()

    updated = models.DateTimeField(auto_now=True)
    network = models.CharField(max_length=16, unique=True)

    coin = models.CharField(max_length=16)

    amount = get_amount_field()
    usdt_value = get_amount_field()
