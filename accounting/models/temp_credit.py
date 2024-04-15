from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from ledger.utils.external_price import SELL
from ledger.utils.fields import get_amount_field, get_group_id_field
from market.models import BaseTrade


class TempCredit(models.Model):
    history = HistoricalRecords()

    user = models.ForeignKey(to='accounts.User', on_delete=models.CASCADE)
    asset = models.ForeignKey(to='ledger.Asset', on_delete=models.CASCADE)
    amount = get_amount_field(decimal_places=2, validators=())

    class Meta:
        unique_together = ('user', 'asset')
