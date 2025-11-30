from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from ledger.utils.fields import get_amount_field


class ExchangeConfig(models.Model):
    active = models.BooleanField(verbose_name='فعال', default=False)

    withdraw_enable = models.BooleanField(verbose_name='برداشت فعال است؟', default=True)
    deposit_enable = models.BooleanField(verbose_name='واریز فعال است؟', default=True)

    class Meta:
        verbose_name = verbose_name_plural = 'مدیریت صرافی'

    @classmethod
    def get_active(cls) -> 'ExchangeConfig':
        return ExchangeConfig.objects.filter(active=True).order_by('id').first() or ExchangeConfig()
