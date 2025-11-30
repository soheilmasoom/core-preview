from django.db import models

from ledger.models import Asset


class CoinCategory(models.Model):
    name = models.CharField(max_length=32, db_index=True)
    coins = models.ManyToManyField(Asset, blank=True)
    binance_name = models.CharField(max_length=32, blank=True)

    title = models.CharField(max_length=32, blank=True)
    description = models.TextField(blank=True)
    order = models.SmallIntegerField(default=0, db_index=True)

    header = models.CharField(max_length=128, blank=True)
    meta_description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = verbose_name = 'گروه‌بندی نمایش رمزارزها'
        ordering = ('order', 'id')

    def __str__(self):
        return self.name
