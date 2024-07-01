import re

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from ledger.utils.fields import get_amount_field, get_status_field, PROCESS, INIT


class ManualWithdraw(models.Model):
    history = HistoricalRecords()

    created = models.DateTimeField(auto_now_add=True)
    receiver_address = models.CharField(max_length=256)
    network = models.ForeignKey('ledger.Network', on_delete=models.CASCADE)
    asset = models.ForeignKey('ledger.Asset', on_delete=models.CASCADE)
    amount = get_amount_field()
    memo = models.CharField(max_length=256, blank=True)
    comment = models.TextField(blank=True)

    status = get_status_field(default=INIT)
    trx_hash = models.CharField(max_length=128, db_index=True, null=True, blank=True)

    def clean(self):
        if self.network.address_regex and not re.match(self.network.address_regex, self.receiver_address):
            raise ValidationError({'receiver_address': 'Invalid Address'})
