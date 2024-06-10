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
class RebrandInfo:
    total_old_amounts: Decimal
    total_new_amounts: Decimal


class TokenRebrand(models.Model):
    created = models.DateTimeField(auto_now=True)

    old_asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='token_rebrand_old')
    new_asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='token_rebrand_new')

    new_asset_multiplier = get_amount_field(default=1)

    status = get_status_field(default=PENDING)

    testers = models.ManyToManyField(User, limit_choices_to={'is_staff': True}, null=True, blank=True)

    group_id = get_group_id_field()

    def clean(self):
        if self.new_asset and self.new_asset == self.old_asset:
            raise ValidationError('new and old asset are same!')

        if self.new_asset_multiplier == 0:
            raise ValidationError('new_asset_multiplier > 0')

        if self.old_asset.rebranded_to or Asset.objects.filter(rebranded_to=self.new_asset):
            raise ValidationError('old or new participated in rebranding before!')

    def reject(self):
        with transaction.atomic():
            rebrand = TokenRebrand.objects.filter(id=self.id, status=PENDING).select_for_update().first()

            if not rebrand:
                return

            rebrand.status = CANCELED
            rebrand.save(update_fields=['status'])

    def accept(self):
        with WalletPipeline() as pipeline:
            rebrand = TokenRebrand.objects.filter(id=self.id, status=PENDING).select_for_update().first()

            if not rebrand:
                return

            self.transfer_funds(pipeline)

            self.old_asset.enable = False
            self.old_asset.rebranded_to = self.new_asset

            self.old_asset.save(update_fields=['enable', 'rebranded_to'])

            rebrand.status = DONE
            rebrand.save(update_fields=['status'])

    def get_candidate_wallets(self, only_testers: bool = False):
        wallets = Wallet.objects.filter(
            asset=self.old_asset,
            market=Wallet.SPOT,
            balance__gt=0,
            account__type__isnull=True
        )

        if only_testers:
            wallets = wallets.filter(account__user__in=self.testers.all())

        return wallets

    def get_rebrand_info(self) -> RebrandInfo:
        if self.status == PENDING:
            total_old = self.get_candidate_wallets().aggregate(
                s=Sum('balance')
            )['s'] or 0

            return RebrandInfo(
                total_old_amounts=humanize_number(total_old),
                total_new_amounts=humanize_number(total_old * self.new_asset_multiplier)
            )
        elif self.status == DONE:
            old_amounts = Trx.objects.filter(
                group_id=self.group_id,
                sender__asset=self.old_asset,
                scope=Trx.REBRAND,
            ).aggregate(s=Sum('amount'))['s'] or 0

            new_amounts = Trx.objects.filter(
                group_id=self.group_id,
                sender__asset=self.new_asset,
                scope=Trx.REBRAND,
            ).aggregate(s=Sum('amount'))['s'] or 0

            return RebrandInfo(
                total_old_amounts=humanize_number(old_amounts),
                total_new_amounts=humanize_number(new_amounts),
            )
        else:
            return RebrandInfo(
                total_new_amounts=Decimal(0),
                total_old_amounts=Decimal(0),
            )

    def transfer_funds(self, pipeline: WalletPipeline, only_testers: bool = False):
        assert self.status == PENDING

        wallets = self.get_candidate_wallets(only_testers=only_testers)

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
                group_id=self.group_id,
                scope=Trx.REBRAND,
            )
            pipeline.new_trx(
                sender=system_new_wallet,
                receiver=self.new_asset.get_wallet(w.account),
                amount=new_balance,
                group_id=self.group_id,
                scope=Trx.REBRAND,
            )

            if self.new_asset_multiplier == 1:
                message = 'با توجه به اطلاع‌رسانی قبلی، توکن {} به {} تغییر نام یافت.'.format(
                    self.old_asset, self.new_asset
                )
            else:
                message = 'با توجه به اطلاع‌رسانی قبلی، توکن {} به {} تغییر نام یافت. در این تغییر، هر توکن {} به {} تا توکن {} تبدیل شد.'.format(
                    self.old_asset, self.new_asset, self.old_asset, get_presentation_amount(self.new_asset_multiplier), self.new_asset
                )

            Notification.send(
                recipient=w.account.user,
                title='تبدیل توکن {} به {}'.format(self.old_asset, self.new_asset),
                message=message,
                level=Notification.INFO,
            )
