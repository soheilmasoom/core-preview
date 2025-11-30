from django.db import models

from accounts.models import Account
from ledger.models import Trx, Wallet
from ledger.utils.fields import get_status_field, DONE, get_group_id_field, get_amount_field
from ledger.utils.wallet_pipeline import WalletPipeline


class ManualTransaction(models.Model):
    DEPOSIT, WITHDRAW = 'd', 'w'

    created = models.DateTimeField(auto_now_add=True)
    group_id = get_group_id_field()

    wallet = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT)
    amount = get_amount_field()

    type = models.CharField(
        max_length=1,
        choices=((DEPOSIT, 'deposit'), (WITHDRAW, 'withdraw')),
    )

    status = get_status_field()
    reason = models.TextField(blank=True)

    allow_debt = models.BooleanField(default=False)

    def change_status(self, status: str):
        if self.status == DONE and status != DONE:
            return

        with WalletPipeline() as pipeline:  # type: WalletPipeline
            amount = self.amount

            if self.status != DONE and status == DONE:
                sender, receiver = self.wallet.asset.get_wallet(Account.system()), self.wallet

                if self.type == self.WITHDRAW:
                    sender, receiver = receiver, sender

                    if self.allow_debt:
                        sender_free = sender.get_free()

                        if sender_free < amount:
                            amount = sender_free

                            pipeline.new_trx(
                                sender=sender.asset.get_wallet(sender.account, market=Wallet.DEBT),
                                receiver=receiver,
                                group_id=self.group_id,
                                scope=Trx.MANUAL,
                                amount=self.amount - sender_free
                            )

                pipeline.new_trx(
                    sender=sender,
                    receiver=receiver,
                    group_id=self.group_id,
                    scope=Trx.MANUAL,
                    amount=amount
                )

            self.status = status
            self.save(update_fields=['status'])
