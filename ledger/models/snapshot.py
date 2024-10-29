from django.db import models
from simple_history.models import HistoricalRecords

from ledger.utils.fields import get_amount_field


class AssetSnapshot(models.Model):
    history = HistoricalRecords()

    updated = models.DateTimeField(db_index=True)
    asset = models.OneToOneField('ledger.Asset', on_delete=models.CASCADE)

    price = get_amount_field()
    hedge_amount = get_amount_field()
    hedge_value = get_amount_field()
    hedge_value_abs = get_amount_field()
    calc_hedge_amount = get_amount_field()

    total_amount = get_amount_field()
    users_amount = get_amount_field()

    def __str__(self):
        return str(self.asset)


class SystemSnapshot(models.Model):
    created = models.DateTimeField(unique=True, db_index=True)
    usdt_price = get_amount_field()
    hedge = get_amount_field(validators=())
    cum_hedge = get_amount_field(validators=())
    binance_margin_ratio = get_amount_field()

    total = get_amount_field()
    users = get_amount_field()
    exchange = get_amount_field(validators=())
    reserved = get_amount_field(validators=())

    margin_insurance = get_amount_field(validators=())
    prize = get_amount_field()

    verified = models.BooleanField(default=False)
    description = models.TextField(null=True, blank=True)
