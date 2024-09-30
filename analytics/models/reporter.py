from django.core.validators import MaxValueValidator
from django.db import models

from ledger.utils.fields import get_group_id_field


class ReportPermission(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    utm_source = models.CharField(max_length=256)
    utm_medium = models.CharField(max_length=256)
    referral_percent_revenue = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])

    enable = models.BooleanField(default=True)
    group_id = get_group_id_field()

    user = models.OneToOneField('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
