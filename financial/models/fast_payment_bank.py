from django.db import models

from financial.utils.manager import ActiveManager


class FastPaymentBank(models.Model):
    objects = models.Manager()
    live_objects = ActiveManager()

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    # deleted = models.BooleanField(default=False)
    active = models.BooleanField(default=False)

    code = models.CharField(max_length=50, verbose_name="کد")
    name = models.CharField(blank=True, null=True, max_length=255, verbose_name="نام")
    is_healthy_on_direct_debit = models.BooleanField(default=True, verbose_name="وضعیت")
    max_withdrawal_amount = models.IntegerField(blank=True, null=True, verbose_name="سقف مجاز مجموع برداشت روزانه")
    max_withdrawal_amount_per_transaction = models.IntegerField(blank=True, null=True, verbose_name="سقف مجاز هر برداشت")
    withdrawal_amount_currency = models.CharField(blank=True, max_length=10,verbose_name="واحد پولی سقف برداشت")
    max_withdrawal_daily_count = models.IntegerField(blank=True, null=True, verbose_name="حداکثر تعداد برداشت روزانه")
    max_mandate_validity_duration = models.IntegerField(blank=True, null=True, verbose_name="حداکثر مدت اعتبار مجوز پرداخت از حساب")
    mandate_validity_duration_unit = models.CharField(blank=True, max_length=50, verbose_name="واحد مدت اعتبار مجوز")
    payer_authentication_type = models.CharField(blank=True, max_length=100, verbose_name="نوع احراز هویت پرداخت‌کننده")

    gateway = models.ForeignKey(
        to='financial.FastPaymentGateway',
        on_delete=models.CASCADE,
        related_name="banks",
        verbose_name="درگاه مرتبط"
    )

    class Meta:
        unique_together = (('code', 'gateway'),)
        verbose_name = "بانک پرداخت سریع"
        verbose_name_plural = "بانک‌های پرداخت سریع"

    def __str__(self):
        return self.name