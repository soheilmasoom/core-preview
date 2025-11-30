from django.db import models
from simple_history.models import HistoricalRecords

from accounts.models import User


class UserComment(models.Model):
    history = HistoricalRecords()

    created = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='کاربر')
    comment = models.TextField(
        verbose_name='نظر'
    )

    class Meta:
        verbose_name = "نظر کاربر"
        verbose_name_plural = "نظر‌های کاربر"

    def __str__(self):
        return 'نظرهای ' + str(self.user)

