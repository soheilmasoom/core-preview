import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Union
from uuid import uuid4

from decouple import config
from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint
from django.db.models import UniqueConstraint, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from simple_history.models import HistoricalRecords

from accounts.models import Account, Notification, EmailNotification, User
from accounts.utils.mask import get_masked_phone
from analytics.event.producer import get_kafka_producer
from analytics.utils.dto import TransferEvent
from ledger.fields import WithdrawSources
from ledger.models import Trx, NetworkAsset, Asset, DepositAddress
from ledger.models import Wallet, Network
from ledger.utils.fields import get_amount_field, get_address_field, CANCELED, DONE, PROCESS, INIT, get_status_field, \
    REFUND
from ledger.utils.precision import humanize_number, get_presentation_amount
from ledger.utils.price import get_last_price
from ledger.utils.revert import revert_trx_group
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)


class Transfer(models.Model):
    history = HistoricalRecords()

    FREEZE_SECONDS = 30

    COMPLETE_STATUSES = (CANCELED, DONE)

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    accepted_datetime = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    finished_datetime = models.DateTimeField(null=True, blank=True, db_index=True)

    accepted_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)

    group_id = models.UUIDField(default=uuid4, db_index=True)
    deposit_address = models.ForeignKey('ledger.DepositAddress', on_delete=models.CASCADE, null=True, blank=True)
    network = models.ForeignKey('ledger.Network', on_delete=models.CASCADE, null=True, blank=True)
    wallet = models.ForeignKey('ledger.Wallet', on_delete=models.CASCADE)

    amount = get_amount_field()
    fee_amount = get_amount_field(default=Decimal(0))

    deposit = models.BooleanField()

    status = get_status_field()

    trx_hash = models.CharField(max_length=128, db_index=True, null=True, blank=True)
    block_number = models.PositiveBigIntegerField(db_index=True, null=True, blank=True)
    last_block_number = models.PositiveBigIntegerField(db_index=True, null=True, blank=True)

    out_address = get_address_field()
    memo = models.CharField(max_length=64, blank=True)

    source = WithdrawSources.get_db_field()
    irt_value = get_amount_field(default=Decimal(0))
    usdt_value = get_amount_field(default=Decimal(0))

    comment = models.TextField(blank=True, verbose_name='نظر')

    risks = models.JSONField(null=True, blank=True)

    address_book = models.ForeignKey('ledger.AddressBook', on_delete=models.PROTECT, null=True, blank=True)
    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    whitelist = models.BooleanField(default=False)

    def in_freeze_time(self):
        return timezone.now() <= self.created + timedelta(seconds=self.FREEZE_SECONDS)

    @property
    def asset(self):
        return self.wallet.asset

    @property
    def total_amount(self):
        return self.amount + self.fee_amount

    @property
    def network_asset(self):
        return NetworkAsset.objects.get(network=self.network, asset=self.asset)

    def get_confirmation_blocks(self) -> Union[int, None]:
        if self.last_block_number and self.block_number:
            return min(max(self.last_block_number - self.block_number, 0), self.network.min_confirm)

    def get_explorer_link(self) -> str:
        if not self.trx_hash:
            return ''

        if 'Internal transfer' in self.trx_hash:
            return ''

        return self.network.explorer_link.format(hash=self.trx_hash)

    def build_trx(self, pipeline: WalletPipeline):
        if self.source == WithdrawSources.INTERNAL_ACCOUNT:
            sender_wallet = self.wallet
            receiver = User.objects.filter(phone=self.out_address).first()
            receiver_wallet = self.wallet.assset.get_wallet(receiver.account)
            pipeline.new_trx(
                group_id=self.group_id,
                sender=sender_wallet,
                receiver=receiver_wallet,
                amount=self.amount,
                scope=Trx.INTERNAL_TRANSFER
            )
            return

        asset = self.wallet.asset
        out_wallet = asset.get_wallet(Account.out())

        if self.deposit:
            sender, receiver = out_wallet, self.wallet
        else:
            sender, receiver = self.wallet, out_wallet

        pipeline.new_trx(
            group_id=self.group_id,
            sender=sender,
            receiver=receiver,
            amount=self.amount,
            scope=Trx.TRANSFER
        )

        if self.fee_amount:
            pipeline.new_trx(
                group_id=self.group_id,
                sender=sender,
                receiver=asset.get_wallet(Account.system()),
                amount=self.fee_amount,
                scope=Trx.COMMISSION
            )

        if self.deposit:
            from gamify.utils import check_prize_achievements, Task
            check_prize_achievements(receiver.account, Task.DEPOSIT)

    @classmethod
    def check_fast_forward(cls, sender_wallet: Wallet, amount: Decimal, receiver_wallet: Union['Wallet', None] = None, address: str = '',
                           memo: str = '', network: Union['Network', None] = None) -> Union['Transfer', None]:

        group_id = uuid4()

        if address:
            queryset = DepositAddress.objects.filter(address=address)

            if network.deposit_need_memo and memo:
                queryset = queryset.filter(address_key__memo=memo)

            if not queryset.exists() or (network.deposit_need_memo and not memo):
                return

            sender_deposit_address = DepositAddress.get_deposit_address(
                account=sender_wallet.account,
                network=network
            )

            receiver_account = queryset.first().address_key.account
            receiver_deposit_address = DepositAddress.get_deposit_address(
                account=receiver_account,
                network=network
            )
            receiver_wallet = sender_wallet.asset.get_wallet(receiver_account)
            scope = Trx.TRANSFER
            trx_hash = 'internal: <%s>' % str(group_id)
            source = WithdrawSources.INTERNAL
            out_address = address
            sender_out_address = sender_deposit_address.address

        elif receiver_wallet:
            sender_deposit_address = None
            receiver_deposit_address = None
            memo = None
            network = None
            trx_hash = 'internal_accoutn: <%s>' % str(group_id)
            scope = Trx.INTERNAL_TRANSFER
            source = WithdrawSources.INTERNAL_ACCOUNT
            out_address = get_masked_phone(receiver_wallet.account.user.username)
            sender_out_address = get_masked_phone(sender_wallet.account.user.username)
            receiver_account = receiver_wallet.account
        else:
            return

        price_usdt = get_last_price(sender_wallet.asset.symbol + Asset.USDT) or 0
        price_irt = get_last_price(sender_wallet.asset.symbol + Asset.IRT) or 0

        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=sender_wallet,
                receiver=receiver_wallet,
                scope=scope,
                group_id=group_id,
                amount=amount
            )
            sender_transfer = Transfer.objects.create(
                status=DONE,
                deposit_address=sender_deposit_address,
                memo=memo,
                wallet=sender_wallet,
                network=network,
                amount=amount,
                deposit=False,
                group_id=group_id,
                trx_hash=trx_hash,
                out_address=out_address,
                source=source,
                usdt_value=amount * price_usdt,
                irt_value=amount * price_irt,
            )

            receiver_transfer = Transfer.objects.create(
                status=DONE,
                deposit_address=receiver_deposit_address,
                memo=memo,
                wallet=receiver_wallet,
                network=network,
                amount=amount,
                deposit=True,
                group_id=group_id,
                trx_hash=trx_hash,
                out_address=sender_out_address,
                source=source,
                usdt_value=amount * price_usdt,
                irt_value=amount * price_irt,
            )

        from gamify.utils import check_prize_achievements, Task
        check_prize_achievements(receiver_account, Task.DEPOSIT)

        sender_transfer.alert_user()
        receiver_transfer.alert_user()

        return sender_transfer

    @classmethod
    def new_withdraw(cls, wallet: Wallet, amount: Decimal, address: str, memo: str = '',
                     whitelist: bool = False, network: Union['Network', None] = None, receiver_wallet: Union['Wallet', None] = None):

        assert wallet.asset.symbol != Asset.IRT
        assert wallet.account.is_ordinary_user()
        wallet.has_balance(amount, raise_exception=True, check_system_wallets=True)

        fast_forward = cls.check_fast_forward(
            receiver_wallet=receiver_wallet,
            sender_wallet=wallet,
            network=network,
            amount=amount,
            address=address,
            memo=memo
        )

        if fast_forward:
            return fast_forward

        network_asset = NetworkAsset.objects.get(network=network, asset=wallet.asset)
        assert network_asset.withdraw_max >= amount >= max(network_asset.withdraw_min, network_asset.withdraw_fee)

        commission = network_asset.withdraw_fee

        price_irt = get_last_price(wallet.asset.symbol + Asset.IRT) or 0
        price_usdt = get_last_price(wallet.asset.symbol + Asset.USDT) or 0

        with WalletPipeline() as pipeline:  # type: WalletPipeline
            transfer = Transfer.objects.create(
                status=INIT,
                wallet=wallet,
                network=network,
                amount=amount - commission,
                fee_amount=commission,
                source=network_asset.withdraw_source,
                out_address=address,
                deposit=False,
                memo=memo,
                usdt_value=amount * price_usdt,
                irt_value=amount * price_irt,
                whitelist=whitelist,
            )

            pipeline.new_lock(key=transfer.group_id, wallet=wallet, amount=amount, reason=WalletPipeline.WITHDRAW)

        from ledger.utils.withdraw_verify import auto_withdraw_verify

        if auto_withdraw_verify(transfer):
            transfer.status = PROCESS
            transfer.save(update_fields=['status'])
        else:
            # send_system_message(
            #     message='INIT %s' % transfer,
            #     link=url_to_edit_object(transfer)
            # )
            pass

        return transfer

    def alert_user(self):
        user = self.wallet.account.user

        if user and user.is_active:
            if self.deposit:
                if self.source == WithdrawSources.INTERNAL_ACCOUNT:
                    title = 'دریافت شد: %s %s' % (humanize_number(self.amount), self.asset.name_fa)
                    message = ''
                    template = 'internal_crypto_deposit_successful'
                else:
                    title = 'دریافت شد: %s %s' % (humanize_number(self.amount), self.wallet.asset.name_fa)
                    message = 'از ادرس %s...%s ' % (self.out_address[-8:], self.out_address[:9])
                    template = 'crypto_deposit_successful'
            else:
                if self.source == WithdrawSources.INTERNAL_ACCOUNT:
                    title = 'ارسال شد: %s %s' % (humanize_number(self.amount), self.asset.name_fa)
                    message = ''
                    template = 'internal_crypto_withdraw_successful'
                else:
                    title = 'ارسال شد: %s %s' % (humanize_number(self.amount), self.wallet.asset.name_fa)
                    message = 'به ادرس %s...%s ' % (self.out_address[-8:], self.out_address[:9])
                    template = 'crypto_withdraw_successful'


            Notification.send(
                recipient=self.wallet.account.user,
                title=title,
                message=message
            )

            EmailNotification.send_by_template(
                recipient=user,
                template=template,
                context={
                    'amount': humanize_number(self.amount),
                    'coin': self.wallet.asset.symbol,
                    'out_address': self.out_address,
                    'trx_hash': self.trx_hash,
                    'brand': settings.BRAND,
                    'panel_url': settings.PANEL_URL,
                    'logo_elastic_url': config('LOGO_ELASTIC_URL', ''),
                }
            )

    def accept(self):
        with WalletPipeline() as pipeline:  # type: WalletPipeline
            transfer = Transfer.objects.select_for_update().get(id=self.id)
            if transfer.status in self.COMPLETE_STATUSES:
                return

            transfer.status = DONE
            transfer.finished_datetime = timezone.now()

            transfer.save(update_fields=['status', 'finished_datetime'])

            if not transfer.deposit:
                pipeline.release_lock(transfer.group_id)

                # We should alert user when deposit transfer created and when withdraw transfer changes to done
                transfer.alert_user()

            else:
                User.objects.filter(
                    id=transfer.wallet.account.user_id,
                    first_crypto_deposit_date__isnull=True
                ).update(
                    first_crypto_deposit_date=timezone.now()
                )

            transfer.build_trx(pipeline)

    def reject(self):
        with WalletPipeline() as pipeline:
            transfer = Transfer.objects.select_for_update().get(id=self.id)
            if transfer.status in self.COMPLETE_STATUSES:
                return

            if not transfer.deposit:
                pipeline.release_lock(transfer.group_id)

            transfer.status = CANCELED
            transfer.finished_datetime = timezone.now()
            transfer.save(update_fields=['status', 'finished_datetime'])

    def revert(self):
        with WalletPipeline() as pipeline:
            transfer = Transfer.objects.select_for_update().get(id=self.id)

            if transfer.status != DONE:
                return

            transfer.status = REFUND
            transfer.save(update_fields=['status'])

            revert_trx_group(pipeline, self.group_id, allow_debt=True)

    def change_status(self, status: str):
        if status == DONE:
            self.accept()
        elif status == CANCELED:
            self.reject()
        elif status == REFUND:
            self.revert()
        else:
            Transfer.objects.filter(
                id=self.id
            ).exclude(
                status__in=self.COMPLETE_STATUSES
            ).update(status=status)

    class Meta:
        constraints = [
            CheckConstraint(check=Q(amount__gte=0, fee_amount__gte=0), name='check_ledger_transfer_amounts', ),
            UniqueConstraint(
                fields=('trx_hash', 'network', 'wallet', 'deposit_address', 'out_address'),
                condition=Q(trx_hash__isnull=False, source='self'),
                name='unique_ledger_transfer_trx_hash_addresses',
            ),
        ]

        permissions = [
            ("list_transfer", "Can list transfer"),
        ]

    def __str__(self):
        if self.deposit:
            action = 'deposit'
        else:
            action = 'withdraw'

        return f'{action} {get_presentation_amount(self.amount)} {self.asset}/{self.network} ' \
               f'({get_presentation_amount(self.usdt_value)}$)'


@receiver(post_save, sender=Transfer)
def handle_transfer_save(sender, instance, created, **kwargs):
    if instance.status != DONE or settings.DEBUG_OR_TESTING_OR_STAGING:
        return

    event = TransferEvent(
        id=instance.id,
        user_id=instance.wallet.account.user_id,
        amount=instance.amount,
        coin=instance.wallet.asset.symbol,
        network=instance.network.symbol if instance.network else None,
        created=instance.created,
        is_deposit=instance.deposit,
        value_irt=instance.irt_value,
        value_usdt=instance.usdt_value,
        event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(instance.id) + TransferEvent.type + 'crypto')
    )

    get_kafka_producer().produce(event)
