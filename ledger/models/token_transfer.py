import dataclasses
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum

from accounts.models import User, Account, Notification
from ledger.models import Asset, Wallet, Trx
from ledger.utils.fields import get_status_field, get_amount_field, CANCELED, DONE, PENDING, get_group_id_field
from ledger.utils.precision import get_presentation_amount, humanize_number
from ledger.utils.wallet_pipeline import WalletPipeline


@dataclasses.dataclass
class TransferInfo:
    total_old_amounts: Decimal
    total_new_amounts: Decimal


class TokenTransfer(models.Model):
    created = models.DateTimeField(auto_now=True)

    title = models.CharField(max_length=256)

    status = get_status_field(default=PENDING)

    group_id = get_group_id_field()

    description = models.TextField(blank=True)

    def __str__(self):
        return self.title

    def reject(self):
        with transaction.atomic():
            token_transfer = TokenTransfer.objects.filter(id=self.id, status=PENDING).select_for_update().first()

            if not token_transfer:
                return

            token_transfer.status = CANCELED
            token_transfer.save(update_fields=['status'])

    def accept(self):
        with WalletPipeline() as pipeline:
            token_transfer = TokenTransfer.objects.filter(id=self.id, status=PENDING).select_for_update().first()

            if not token_transfer:
                return

            for part in self.parts.all():
                part.transfer_funds(pipeline)

            token_transfer.status = DONE
            token_transfer.save(update_fields=['status'])


class TokenTransferPart(models.Model):
    token_transfer = models.ForeignKey(TokenTransfer, on_delete=models.CASCADE, related_name='parts')

    old_asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='token_transfers_old')
    new_asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='token_transfers_new')

    new_asset_multiplier = get_amount_field(default=1)

    def __str__(self):
        return f'{self.old_asset} -> {get_presentation_amount(self.new_asset_multiplier)} {self.new_asset}'

    def clean(self):
        if self.new_asset and self.new_asset == self.old_asset:
            raise ValidationError('new and old asset are same!')

        if self.new_asset_multiplier == 0:
            raise ValidationError('new_asset_multiplier > 0')

    def get_candidate_wallets(self):
        wallets = Wallet.objects.filter(
            asset=self.old_asset,
            market=Wallet.SPOT,
            balance__gt=0,
            account__type__isnull=True
        )

        return wallets

    def get_transfer_info(self) -> TransferInfo:
        if self.token_transfer.status == PENDING:
            total_old = self.get_candidate_wallets().aggregate(
                s=Sum('balance')
            )['s'] or 0

            return TransferInfo(
                total_old_amounts=humanize_number(total_old),
                total_new_amounts=humanize_number(total_old * self.new_asset_multiplier)
            )

        elif self.token_transfer.status == DONE:
            old_amounts = Trx.objects.filter(
                group_id=self.token_transfer.group_id,
                sender__asset=self.old_asset,
                scope=Trx.TOKEN_TRANSFER,
            ).aggregate(s=Sum('amount'))['s'] or 0

            new_amounts = Trx.objects.filter(
                group_id=self.token_transfer.group_id,
                sender__asset=self.new_asset,
                scope=Trx.TOKEN_TRANSFER,
            ).aggregate(s=Sum('amount'))['s'] or 0

            return TransferInfo(
                total_old_amounts=humanize_number(old_amounts),
                total_new_amounts=humanize_number(new_amounts),
            )
        else:
            return TransferInfo(
                total_new_amounts=Decimal(0),
                total_old_amounts=Decimal(0),
            )

    def transfer_funds(self, pipeline: WalletPipeline):
        assert self.token_transfer.status == PENDING
        group_id = self.token_transfer.group_id

        wallets = self.get_candidate_wallets()

        system = Account.system()
        system_old_wallet = self.old_asset.get_wallet(system)
        system_new_wallet = self.new_asset.get_wallet(system)

        for w in wallets:
            balance = w.balance
            new_balance = balance * self.new_asset_multiplier

            pipeline.new_trx(
                sender=w,
                receiver=system_old_wallet,
                amount=balance,
                group_id=group_id,
                scope=Trx.TOKEN_TRANSFER,
            )
            pipeline.new_trx(
                sender=system_new_wallet,
                receiver=self.new_asset.get_wallet(w.account),
                amount=new_balance,
                group_id=group_id,
                scope=Trx.TOKEN_TRANSFER,
            )

            message = 'توکن {} به {} تبدیل شد. در این تبدیل، هر توکن {} به {} تا توکن {} تبدیل شد.'.format(
                self.old_asset, self.new_asset, self.old_asset, get_presentation_amount(self.new_asset_multiplier), self.new_asset
            )

            Notification.send(
                recipient=w.account.user,
                title='تبدیل توکن {} به {}'.format(self.old_asset, self.new_asset),
                message=message,
                level=Notification.INFO,
            )
