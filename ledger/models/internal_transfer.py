from datetime import timedelta
import logging
from decimal import Decimal
from uuid import uuid4
from django.conf import settings
from decouple import config

from django.db import models
from django.db.models import CheckConstraint, Q
from simple_history.models import HistoricalRecords
from django.utils import timezone

from accounts.models import Account
from ledger.models import Wallet, Trx, Asset
from ledger.utils.fields import CANCELED, DONE, PENDING, get_amount_field, get_status_field
from ledger.utils.wallet_pipeline import WalletPipeline
from ledger.utils.precision import humanize_number
from accounts.models import Account, Notification, EmailNotification, User

logger = logging.getLogger(__name__)

class InternalTransfer(models.Model):
    # COMPLETE_STATUSES = (CANCELED, DONE)

    # FREEZE_SECONDS = 30

    # history = HistoricalRecords()
    # created = models.DateTimeField(auto_now_add=True, db_index=True)
    # group_id = models.UUIDField(default=uuid4, db_index=True)
    # sender_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='sent_internal_transfers')
    # receiver_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='received_internal_transfers')
    # amount = get_amount_field()
    # status = get_status_field()
    # asset = models.ForeignKey(to='ledger.Asset', on_delete=models.PROTECT)
    # description = models.TextField(blank=True)
    # login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    # def in_freeze_time(self):
    #     return timezone.now() <= self.created + timedelta(seconds=self.FREEZE_SECONDS)

    @classmethod
    def new_internal_transfer(cls, asset: Asset, sender_account: Account, receiver_account: Account, amount: Decimal, description: str = ''):
        sender_wallet = asset.get_wallet(sender_account)
        sender_wallet.has_balance(amount, raise_exception=True)

        return InternalTransfer.objects.create(
            sender_account=sender_account,
            receiver_account=receiver_account,
            amount=amount,
            asset=asset,
            status=PENDING,
            description=description
            )

    def accept(self):
        with WalletPipeline() as pipeline:
            transfer = InternalTransfer.objects.select_for_update().get(id=self.id)
            if transfer.status in self.COMPLETE_STATUSES:
                return

            transfer.status = DONE
            transfer.save(update_fields=['status'])

            sender_wallet = self.asset.get_wallet(self.sender_account)
            receiver_wallet = self.asset.get_wallet(self.receiver_account)

            pipeline.new_trx(
                group_id=self.group_id,
                sender=sender_wallet,
                receiver=receiver_wallet,
                amount=self.amount,
                scope=Trx.INTERNAL_TRANSFER
            )

    def reject(self):
        if self.status in self.COMPLETE_STATUSES:
            return

        self.status = CANCELED
        self.save(update_fields=['status'])

    def change_status(self, status: str):
        if status == DONE:
            self.accept()
        elif status == CANCELED:
            self.reject()
        else:
            InternalTransfer.objects.filter(
                id=self.id
            ).exclude(
                status__in=self.COMPLETE_STATUSES
            ).update(status=status)


    def alert_user(self):
        sender_user = self.sender_account.user
        receiver_user = self.receiver_account.user

        receiver_title = 'دریافت شد: %s %s' % (humanize_number(self.amount), self.asset.name_fa)
        receiver_message = ''
        receiver_template = 'internal_crypto_deposit_successful'

        sender_title = 'ارسال شد: %s %s' % (humanize_number(self.amount), self.asset.name_fa)
        sender_message = ''
        sender_template = 'internal_crypto_withdraw_successful'

        Notification.send(
            recipient=sender_user,
            title=sender_title,
            message=sender_message
        )
        Notification.send(
            recipient=receiver_user,
            title=receiver_title,
            message=receiver_message
        )
        EmailNotification.send_by_template(
            recipient=receiver_template,
            template=receiver_template,
            context={
                'amount': humanize_number(self.amount),
                'coin': self.asset.symbol,
                'brand': settings.BRAND,
                'panel_url': settings.PANEL_URL,
                'logo_elastic_url': config('LOGO_ELASTIC_URL', ''),
            }
        )
        EmailNotification.send_by_template(
            recipient=sender_user,
            template=sender_template,
            context={
                'amount': humanize_number(self.amount),
                'coin': self.asset.symbol,
                'brand': settings.BRAND,
                'panel_url': settings.PANEL_URL,
                'logo_elastic_url': config('LOGO_ELASTIC_URL', ''),
            }
        )

    class Meta:
        ordering = ['-created']
        constraints = [
                CheckConstraint(
                    check=~Q(sender_account=models.F('receiver_account')),
                    name='sender_receiver_not_equal'
                )
            ]

    def __str__(self):
        return f"Internal Transfer: {self.amount} from {self.sender_account} to {self.receiver_account}"
