from django.db import models

from accounting.models import Account


class AccountTransaction(models.Model):
    DEPOSIT, WITHDRAW = 'd', 'w'

    created = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ')
    updated = models.DateTimeField(auto_now=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, verbose_name='حساب')
    amount = models.PositiveIntegerField(verbose_name='مقدار')
    reason = models.CharField(max_length=128, verbose_name='علت')
    type = models.CharField(max_length=1, verbose_name='نوع', choices=((DEPOSIT, 'واریز'), (WITHDRAW, 'برداشت')))

    def __str__(self):
        return '%s %s' % (self.reason, self.amount)

    class Meta:
        verbose_name = 'تراکنش'
        verbose_name_plural = 'تراکنش‌ها'
