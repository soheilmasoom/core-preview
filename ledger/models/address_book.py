from datetime import timedelta

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .asset import Asset
from .network import Network
from accounts.models import Account
from ledger.models.transfer import Transfer


class AddressBook(models.Model):
    history = HistoricalRecords()

    name = models.CharField(max_length=100, verbose_name='نام')
    address = models.CharField(max_length=100, verbose_name='آدرس')
    account = models.ForeignKey(to=Account, on_delete=models.CASCADE, verbose_name='حساب')
    network = models.ForeignKey(to=Network, on_delete=models.CASCADE, verbose_name='شبکه')
    asset = models.ForeignKey(to=Asset, blank=True, null=True, on_delete=models.CASCADE, verbose_name='رمزارز')
    deleted = models.BooleanField(default=False)
    whitelist = models.BooleanField(default=False)
    memo = models.CharField(max_length=64, blank=True)

    @staticmethod
    def is_address_used_in_24h(address: str) -> bool:
        return Transfer.objects.filter(
            deposit=False,
            out_address=address,
            created__gte=timezone.now() - timedelta(days=1)
        ).exists()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'دفترچه آدرس‌ها'
        verbose_name_plural = 'دفترچه‌های آدرس'
