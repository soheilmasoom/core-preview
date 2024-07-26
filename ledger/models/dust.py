import logging
from uuid import uuid4
from datetime import timedelta
from django.utils import timezone

from django.db import models
from django.db.models import CheckConstraint, Q
from ledger.models.wallet import Wallet

from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class Dust(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='sent_dust_trx')
    receiver = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='received_dust_trx')
    amount = get_amount_field()
    converted_amount = get_amount_field()
    base_asset = models.ForeignKey('Asset', on_delete=models.CASCADE)
    group_id = models.UUIDField(default=uuid4, db_index=True)

    class Meta:
        unique_together = ('group_id', 'sender', 'receiver')
        constraints = [
            CheckConstraint(check=Q(amount__gt=0), name='check_ledger_dust_amount', ),
        ]
        indexes = [
            models.Index(fields=['sender', 'created'], name="ledger_dust_sender_created_idx")
        ]

    def save(self, *args, **kwargs):
        assert self.sender.asset == self.receiver.asset
        assert self.sender != self.receiver
        assert self.amount > 0
        assert self.converted_amount > 0

        return super(Dust, self).save(*args, **kwargs)

    @classmethod
    def has_recent_conversion(cls, account, in_last_hour: int = 12):
        return Dust.objects.filter(
                sender__account=account,
                created__gte=timezone.now() - timedelta(hours=in_last_hour)
            ).exists()
