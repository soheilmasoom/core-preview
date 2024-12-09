from django.db import models

from accounts.models import User
from financial.utils.manager import LiveManager


class BaseBankEntity(models.Model):
    REJECT_REASONS = DUPLICATED, NAME_MISMATCH, CREDIT_CARD, MANUAL, TRANSACTION_REFUND = 'duplicated', 'name.mismatch', 'type.credit', 'manual', 'trx_refund'

    objects = models.Manager()
    live_objects = LiveManager()

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)

    verified = models.BooleanField(null=True, blank=True)
    deleted = models.BooleanField(default=False)

    verifier = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    reject_reason = models.CharField(max_length=128, blank=True)

    comment = models.TextField(blank=True)

    class Meta:
        abstract = True

    def reject(self, reason: str, verifier: User = None):
        if self.verified is not False:
            self.verified = False
            self.reject_reason = reason
            self.verifier = verifier
            self.save(update_fields=['verified', 'reject_reason', 'verifier'])

    def accept(self, verifier: User = None):
        self.verified = True
        self.verifier = verifier
        self.save(update_fields=['verified', 'verifier'])
