import logging

from django.db import models
from django.db.models import CheckConstraint, Q

from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class BalanceLock(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    key = models.UUIDField(unique=True, null=True)
    wallet = models.ForeignKey('ledger.Wallet', on_delete=models.CASCADE)

    original_amount = get_amount_field()
    amount = get_amount_field()

    reason = models.CharField(
        max_length=8,
        null=True,
        blank=True
    )

    def __str__(self):
        return '%s %s/%s' % (self.wallet, self.amount, self.original_amount)

    class Meta:
        constraints = [CheckConstraint(check=Q(amount__gte=0), name='check_ledger_balance_lock_amount', ), ]
