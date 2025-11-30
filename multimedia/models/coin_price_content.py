from django.db import models

from simple_history.models import HistoricalRecords
from tinymce.models import HTMLField


class CoinPriceContent(models.Model):
    asset = models.OneToOneField(to='ledger.Asset', on_delete=models.PROTECT)
    content = HTMLField()

    history = HistoricalRecords()

    def __str__(self):
        return str(self.asset)

    def get_html(self):
        return self.content.replace('\r\n', '')

    class Meta:
        verbose_name = 'توضیحات کوین'
        verbose_name_plural = 'توضیحات کوین‌ها'
