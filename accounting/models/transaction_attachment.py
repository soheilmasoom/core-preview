from django.db import models

from accounting.models import AccountTransaction


class TransactionAttachment(models.Model):
    INVOICE, RECEIPT = 'invoice', 'receipt'
    TYPE_CHOICES = ((INVOICE, 'فاکتور'), (RECEIPT, 'رسید'))

    created = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ')
    type = models.CharField(max_length=16, verbose_name='نوع', blank=True, choices=TYPE_CHOICES)
    file = models.FileField(upload_to='accounting/attachments/', verbose_name='ضمیمه')
    transaction = models.ForeignKey(AccountTransaction, on_delete=models.CASCADE)

    def __str__(self):
        return self.file.name

    class Meta:
        verbose_name = 'ضمیمه'
        verbose_name_plural = 'ضمیمه‌ها'
