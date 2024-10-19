from django.db import models

from ledger.utils.fields import get_amount_field


class TransactionHistory(models.Model):
    created = models.DateTimeField()
    group_id = models.UUIDField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    status = models.CharField(max_length=16)
    type = models.CharField(max_length=16)
    amount = get_amount_field()
    coin = models.CharField(max_length=64)

    class Meta:
        db_table = 'ledger_transaction_history_view'
        managed = False
