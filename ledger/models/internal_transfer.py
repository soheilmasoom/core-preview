import logging
from decimal import Decimal
from uuid import uuid4

from django.db import models
from django.db.models import CheckConstraint, Q
from simple_history.models import HistoricalRecords

from accounts.models import Account
from ledger.models import Wallet, Trx
from ledger.utils.fields import get_amount_field, get_status_field
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)

class InternalTransfer(models.Model):
    PENDING = 'pending'
    DONE = 'done'

    history = HistoricalRecords()
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    group_id = models.UUIDField(default=uuid4, db_index=True)
    sender_wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='sent_internal_transfers')
    receiver_wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='received_internal_transfers')
    amount = get_amount_field()
    status = get_status_field()
    description = models.TextField(blank=True)
    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def asset(self):
        return self.sender_wallet.asset

    def build_trx(self, pipeline: WalletPipeline):
        pipeline.new_trx(
            group_id=self.group_id,
            sender=self.sender_wallet,
            receiver=self.receiver_wallet,
            amount=self.amount,
            scope=Trx.INTERNAL_TRANSFER
        )

    @classmethod
    def new_internal_transfer(cls, sender_wallet: Wallet, receiver_wallet: Wallet, amount: Decimal, description: str = ''):
        sender_wallet.has_balance(amount, raise_exception=True)

        with WalletPipeline() as pipeline:
            transfer = InternalTransfer.objects.create(
                sender_wallet=sender_wallet,
                receiver_wallet=receiver_wallet,
                amount=amount,
                status=InternalTransfer.PENDING,
                description=description
            )
        return transfer

    def accept(self):
        with WalletPipeline() as pipeline:
            transfer = InternalTransfer.objects.select_for_update().get(id=self.id)
            if transfer.status == self.DONE:
                return

            transfer.status = self.DONE
            transfer.save(update_fields=['status'])

            transfer.build_trx(pipeline)

    def change_status(self, status: str):
        if status == self.DONE:
            self.accept()
        else:
            InternalTransfer.objects.filter(
                id=self.id
            ).exclude(
                status=self.DONE
            ).update(status=status)


    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"Internal Transfer: {self.amount} {self.asset.symbol} from {self.sender_wallet.account} to {self.receiver_wallet.account}"
