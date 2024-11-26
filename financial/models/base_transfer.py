import logging

from django.db import models

from financial.models import BankAccount
from ledger.utils.fields import get_group_id_field

logger = logging.getLogger(__name__)


class BaseTransfer(models.Model):
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    amount = models.PositiveIntegerField(verbose_name='میزان برداشت')
    gateway = models.ForeignKey('Gateway', on_delete=models.PROTECT)
    bank_account = models.ForeignKey(to=BankAccount, on_delete=models.PROTECT, verbose_name='حساب بانکی')
    group_id = get_group_id_field()
    ref_id = models.CharField(max_length=128, blank=True, verbose_name='شماره پیگیری')

    class Meta:
        abstract = True
