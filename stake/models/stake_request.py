from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Account, User, EmailNotification
from accounts.tasks import send_message_by_kavenegar
from accounts.utils.admin import url_to_edit_object
from accounts.utils.telegram import send_support_message
from ledger.models import Wallet, Trx
from ledger.utils.fields import get_group_id_field, get_amount_field
from ledger.utils.wallet_pipeline import WalletPipeline
from stake.models import StakeOption


class StakeRequest(models.Model):

    PROCESS, PENDING, DONE, FINISHED = 'process', 'pending', 'done', 'finished'
    CANCEL_PROCESS, CANCEL_PENDING, CANCEL_COMPLETE = 'cancel_process', 'cancel_pending', 'cancel_complete'

    STATUS_CHOICE = (
        (PROCESS, PROCESS), (PENDING, PENDING), (DONE, DONE), (CANCEL_PROCESS, CANCEL_PROCESS),
        (CANCEL_PENDING, CANCEL_PENDING), (CANCEL_COMPLETE, CANCEL_COMPLETE), (FINISHED, FINISHED)
    )

    status = models.CharField(choices=STATUS_CHOICE, max_length=16, default=PROCESS)

    stake_option = models.ForeignKey(StakeOption, on_delete=models.CASCADE)

    amount = get_amount_field()

    group_id = get_group_id_field()

    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    created = models.DateTimeField(auto_now_add=True)
    start_at = models.DateTimeField(null=True, blank=True)
    cancel_request_at = models.DateTimeField(null=True, blank=True)
    cancel_pending_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    @property
    def remaining_date(self):
        if self.status in (StakeRequest.PROCESS, StakeRequest.PENDING, StakeRequest.DONE):
            return (self.created + timedelta(days=90)) - timezone.now()

    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return str(self.stake_option) + ' ' + str(self.account_id)

    def get_locked_amount(self) -> Decimal:
        locked_revenue = \
            self.stakerevenue_set.filter(wallet_source=Wallet.STAKE).aggregate(amount=Sum('revenue'))['amount'] or 0

        stake_wallet = self.stake_option.asset.get_wallet(account=self.account, market=Wallet.STAKE)

        return min(self.amount + locked_revenue, stake_wallet.balance)

    def send_email_for_staking(self, user: User, template: str):
        EmailNotification.send_by_template(
            recipient=user,
            template=template,
            context={'coin': self.stake_option.asset.name_fa, 'amount': self.amount},
        )

    def change_status(self, new_status: str):
        old_status = self.status
        account = self.account
        asset = self.stake_option.asset

        valid_change_status = [
            (self.PROCESS, self.PENDING), (self.PROCESS, self.DONE), (self.PROCESS, self.CANCEL_COMPLETE),
            (self.PENDING, self.DONE), (self.PENDING, self.CANCEL_PROCESS),
            (self.DONE, self.CANCEL_PROCESS),
            (self.PROCESS, self.CANCEL_PENDING), (self.PENDING, self.CANCEL_PENDING), (self.CANCEL_PROCESS, self.CANCEL_PENDING),
            (self.DONE, self.CANCEL_COMPLETE), (self.CANCEL_PENDING, self.CANCEL_COMPLETE), (self.CANCEL_PROCESS, self.CANCEL_COMPLETE),
            (self.DONE, self.FINISHED),
        ]

        assert (old_status, new_status) in valid_change_status, 'invalid change_status'

        updating_datetime_field_mapping = {
            self.CANCEL_PROCESS: 'cancel_request_at',
            self.CANCEL_PENDING: 'cancel_pending_at',
            self.CANCEL_COMPLETE: 'end_at',
            self.DONE: 'start_at',
            self.FINISHED: 'end_at'
        }
        updating_field = updating_datetime_field_mapping.get(new_status)
        if updating_field:
            setattr(self, updating_field, timezone.now())

        if new_status == self.CANCEL_COMPLETE and \
                old_status in [self.PROCESS, self.CANCEL_PROCESS, self.CANCEL_PENDING, self.DONE]:

            spot_wallet = asset.get_wallet(account)
            stake_wallet = asset.get_wallet(account=account, market=Wallet.STAKE)

            system_stake_wallet = asset.get_wallet(account=Account.system(), market=Wallet.STAKE)
            stake_fee = self.stake_option.fee

            with WalletPipeline() as pipeline:
                amount = self.get_locked_amount()

                if old_status != self.PROCESS and stake_fee > 0:
                    amount -= stake_fee
                    pipeline.new_trx(
                        group_id=self.group_id,
                        amount=stake_fee,
                        sender=stake_wallet,
                        receiver=system_stake_wallet,
                        scope=Trx.STAKE_FEE,
                    )
                pipeline.new_trx(
                    group_id=self.group_id,
                    sender=stake_wallet,
                    receiver=spot_wallet,
                    amount=amount,
                    scope=Trx.STAKE
                )
                self.status = new_status
                self.save()

            self.send_email_for_staking(account.user, template='staking_canceled')

        elif (old_status, new_status) == (self.DONE, self.FINISHED):
            spot_wallet = asset.get_wallet(account)
            stake_wallet = asset.get_wallet(account=account, market=Wallet.STAKE)

            with WalletPipeline() as pipeline:
                amount = self.get_locked_amount()

                pipeline.new_trx(
                    group_id=self.group_id,
                    sender=stake_wallet,
                    receiver=spot_wallet,
                    amount=amount,
                    scope=Trx.STAKE
                )
                self.status = new_status
                self.save()

            send_message_by_kavenegar(
                phone=account.user.phone,
                token=asset.name_fa,
                send_type='sms',
                template='staking-finished'
            )

        elif (old_status, new_status) in [(self.PROCESS, self.DONE), (self.PENDING, self.DONE)]:
            self.status = new_status
            self.save()
            self.send_email_for_staking(account.user, template='staking_activated')

            send_message_by_kavenegar(
                phone=account.user.phone,
                token=asset.name_fa,
                send_type='sms',
                template='staking-activated'
            )

        elif (old_status, new_status) in [(self.PENDING, self.CANCEL_PROCESS), (self.DONE, self.CANCEL_PROCESS)]:
            self.status = new_status
            self.save()
            link = url_to_edit_object(self)
            send_support_message(
                message='ثبت درخواست لغو staking برای {} {}'.format(self.stake_option.asset, self.amount, ),
                link=link
            )

        else:
            self.status = new_status
            self.save()
