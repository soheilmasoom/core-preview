from django.db import models
from simple_history.models import HistoricalRecords


class ManualAddressBook(models.Model):
    history = HistoricalRecords()

    name = models.CharField(max_length=100, verbose_name='نام')
    address = models.CharField(max_length=256, verbose_name='آدرس')
    network = models.ForeignKey('ledger.Network', on_delete=models.CASCADE, verbose_name='شبکه')
    memo = models.CharField(max_length=256, blank=True)

    deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    # class Meta:
    #     unique_together = ('address', 'network')
    # verbose_name = 'دفترچه آدرس‌ها '
    # verbose_name_plural = 'دفترچه‌های آدرس'
