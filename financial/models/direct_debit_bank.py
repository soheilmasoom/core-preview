from django.db import models

from financial.utils.manager import ActiveManager
from ledger.utils.fields import get_bank_field


class DirectDebitBank(models.Model):
    objects = models.Manager()
    live_objects = ActiveManager()

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)

    bank = get_bank_field()

    max_withdrawal_amount = models.PositiveIntegerField(blank=True, null=True, verbose_name="سقف مجاز مجموع برداشت روزانه")
    max_withdrawal_amount_per_transaction = models.PositiveIntegerField(blank=True, null=True, verbose_name="سقف مجاز هر برداشت")
    max_withdrawal_daily_count = models.PositiveIntegerField(blank=True, null=True, verbose_name="حداکثر تعداد برداشت روزانه")
    max_validity_duration_days = models.PositiveIntegerField(blank=True, null=True, verbose_name="مدت اعتبار مجوز")
    kyc_type = models.CharField(blank=True, max_length=100, verbose_name="نوع احراز هویت پرداخت‌کننده")

    gateway = models.ForeignKey(
        to='financial.DirectDebitGateway',
        on_delete=models.CASCADE,
        related_name="banks",
        verbose_name="درگاه"
    )

    class Meta:
        unique_together = (('bank', 'gateway'),)

    def __str__(self):
        return f'{self.gateway.title} {self.bank}'
