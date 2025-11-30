from django.db import models

from ledger.utils.fields import get_created_field, get_amount_field


class ProviderIncome(models.Model):
    created = get_created_field()

    income_date = models.DateTimeField()
    symbol = models.CharField(max_length=64)
    income_type = models.CharField(max_length=64)
    tran_id = models.CharField(max_length=64, db_index=True, unique=True)
    income = get_amount_field(validators=())
    coin = models.CharField(max_length=32)
