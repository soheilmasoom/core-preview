from django.db import models
from .withdraw_request import BaseTransfer


class ManualTransfer(BaseTransfer):
    PROCESS, DONE = 'process', 'done'
    reason = models.TextField(blank=True)
    bank_account = models.ForeignKey(
        'financial.BankAccount',
        on_delete=models.CASCADE,
        limit_choices_to={'stake_holder': True}
    )
    status = models.CharField(max_length=8, default=PROCESS, choices=((PROCESS, PROCESS), (DONE, DONE)))

    def __str__(self):
        return '%s IRT to %s' % (self.amount, self.bank_account)
