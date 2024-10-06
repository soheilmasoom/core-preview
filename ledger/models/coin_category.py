from django.db import models
from django_quill.fields import QuillField
from simple_history.models import HistoricalRecords

from ledger.models import Asset
from multimedia.utils.custom_tags import post_render_html


class CoinCategory(models.Model):
    history = HistoricalRecords()

    name = models.CharField(max_length=32, db_index=True)
    coins = models.ManyToManyField(Asset, blank=True)
    binance_name = models.CharField(max_length=32, blank=True)

    title = models.CharField(max_length=32, blank=True)

    description = QuillField(blank=True)
    _description_html = models.TextField(blank=True)

    order = models.SmallIntegerField(default=0, db_index=True)

    header = models.CharField(max_length=128, blank=True)
    meta_description = models.TextField(blank=True)

    def refresh(self):
        html = self.description.html
        self._description_html = post_render_html(html)

        self.save(update_fields=['_description_html'])

    class Meta:
        verbose_name_plural = verbose_name = 'گروه‌بندی نمایش رمزارزها'
        ordering = ('order', 'id')

    def __str__(self):
        return self.name
