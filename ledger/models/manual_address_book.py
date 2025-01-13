import re

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords


class ManualAddressBook(models.Model):
    history = HistoricalRecords()

    name = models.CharField(max_length=100, verbose_name='نام')
    address = models.CharField(max_length=256, verbose_name='آدرس')
    network = models.ForeignKey('ledger.Network', on_delete=models.CASCADE, verbose_name='شبکه')
    memo = models.CharField(max_length=256, blank=True)

    deleted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('address', 'network', 'memo')

    def __str__(self):
        return self.name

    def clean(self):
        if self.network.address_regex and not re.match(self.network.address_regex, self.address):
            raise ValidationError({'receiver_address': 'Invalid Address'})

        if self.memo and self.network.memo_regex and not re.match(self.network.memo_regex, self.memo):
            raise ValidationError({'memo': 'Invalid Memo'})
