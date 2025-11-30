from django.db import models

from accounts.models import User
from ledger.utils.fields import get_status_field


class Consultation(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='کاربر'
    )

    consulter = models.ForeignKey(
        User,
        limit_choices_to={'is_staff': True},
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='مشاور',
        related_name='consulters'
    )

    status = get_status_field()
    description = models.TextField(null=True, blank=True, verbose_name='توضیحات کاربر')
    comment = models.TextField(null=True, blank=True, verbose_name='نظر مشاور')

    class Meta:
        verbose_name_plural = 'درخواست ‌های مشاوره'
        verbose_name = 'درخواست مشاوره'
