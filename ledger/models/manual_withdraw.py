import re

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from ledger.utils.fields import get_amount_field, get_status_field, INIT


class ManualWithdraw(models.Model):
    history = HistoricalRecords()

    created = models.DateTimeField(auto_now_add=True)
    address_book = models.ForeignKey('ledger.ManualAddressBook', on_delete=models.CASCADE)
    asset = models.ForeignKey('ledger.Asset', on_delete=models.CASCADE)
    amount = get_amount_field()
    comment = models.TextField(blank=True)

    status = get_status_field(default=INIT)
    trx_hash = models.CharField(max_length=128, db_index=True, null=True, blank=True)

    def clean(self):
        if self.address_book.network.address_regex and not re.match(self.address_book.network.address_regex,
                                                                    self.address_book.address):
            raise ValidationError({'receiver_address': 'Invalid Address'})

        if self.address_book.memo and self.address_book.network.memo_regex and not re.match(
                self.address_book.network.memo_regex, self.address_book.memo):
            raise ValidationError({'memo': 'Invalid Memo'})

    def __str__(self):
        return f'Manual withdraw {self.amount} {self.asset}/{self.address_book.network}'
