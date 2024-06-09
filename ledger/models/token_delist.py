import dataclasses
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum

from accounts.models import User, Account, Notification
from ledger.models import Asset, Wallet, Trx
from ledger.utils.external_price import BUY
from ledger.utils.fields import get_status_field, CANCELED, DONE, PENDING, get_group_id_field
from ledger.utils.precision import humanize_number
from ledger.utils.price import get_price
from ledger.utils.wallet_pipeline import WalletPipeline


@dataclasses.dataclass
class DelistInfo:
    asset_amounts: Decimal
    base_amounts: Decimal


class TokenDelist(models.Model):
    created = models.DateTimeField(auto_now=True)

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    status = get_status_field(default=PENDING)

    testers = models.ManyToManyField(User, limit_choices_to={'is_staff': True}, null=True, blank=True)
    group_id = get_group_id_field()

    def clean(self):
        if self.asset.otc_status == Asset.ACTIVE:
            raise ValidationError('Asset should not be active!')

        if not self.asset.enable:
            raise ValidationError('Asset should be enable!')

    def reject(self):
        with transaction.atomic():
            delist = TokenDelist.objects.filter(id=self.id, status=PENDING).select_for_update().first()

            if not delist:
                return

            delist.status = CANCELED
            delist.save(update_fields=['status'])

    def accept(self):
        with WalletPipeline() as pipeline:
            delist = TokenDelist.objects.filter(id=self.id, status=PENDING).select_for_update().first()

            if not delist:
                return

            self.change_funds(pipeline)

            self.asset.enable = False
            self.asset.price_page = True
            self.asset.save(update_fields=['enable', 'price_page'])

            delist.status = DONE
            delist.save(update_fields=['status'])

    def get_candidate_wallets(self, only_testers: bool = False):
        wallets = Wallet.objects.filter(
            asset=self.asset,
            market=Wallet.SPOT,
            balance__gt=0,
            account__type=Account.ORDINARY
        )

        if only_testers:
            wallets = wallets.filter(account__user__in=self.testers.all())

        return wallets

    def get_delist_info(self) -> DelistInfo:
        asset = self.asset
        base_asset = Asset.get(Asset.IRT)

        if self.status == PENDING:
            amount_sum = self.get_candidate_wallets().aggregate(
                s=Sum('balance')
            )['s'] or 0

            price = get_price(
                asset.symbol + Asset.IRT,
                side=BUY,
            )

            return DelistInfo(
                asset_amounts=humanize_number(amount_sum),
                base_amounts=humanize_number(amount_sum * price)
            )

        elif self.status == DONE:
            asset_amounts = Trx.objects.filter(
                group_id=self.group_id,
                sender__asset=asset,
                scope=Trx.DELIST,
            ).aggregate(s=Sum('amount'))['s'] or 0

            base_amounts = Trx.objects.filter(
                group_id=self.group_id,
                sender__asset=base_asset,
                scope=Trx.DELIST,
            ).aggregate(s=Sum('amount'))['s'] or 0

            return DelistInfo(
                asset_amounts=humanize_number(asset_amounts),
                base_amounts=humanize_number(base_amounts),
            )
        else:
            return DelistInfo(
                asset_amounts=Decimal(0),
                base_amounts=Decimal(0),
            )

    def change_funds(self, pipeline: WalletPipeline, only_testers: bool = False):
        asset = self.asset
        base_asset = Asset.get(Asset.IRT)

        assert self.status == PENDING
        assert asset.otc_status != Asset.ACTIVE
        assert asset != base_asset

        wallets = self.get_candidate_wallets(only_testers=only_testers).prefetch_related('account__user')

        system_asset_wallet = asset.get_wallet(Account.system())
        system_base_asset_wallet = base_asset.get_wallet(Account.system())

        price = get_price(
            asset.symbol + base_asset.symbol,
            side=BUY,
        )

        for wallet in wallets:
            amount = wallet.balance
            base_amount = amount * price

            pipeline.new_trx(
                sender=wallet,
                receiver=system_asset_wallet,
                amount=amount,
                group_id=self.group_id,
                scope=Trx.DELIST,
            )
            pipeline.new_trx(
                sender=system_base_asset_wallet,
                receiver=base_asset.get_wallet(wallet.account),
                amount=base_amount,
                group_id=self.group_id,
                scope=Trx.DELIST,
            )

            if base_amount >= 1:
                Notification.send(
                    recipient=wallet.account.user,
                    title='تبدیل خودکار توکن {}'.format(asset.symbol),
                    message='با توجه به اطلاع‌رسانی‌های قبلی مبنی بر حذف توکن {}، مقدار {} {} به {} تومان تبدیل شد.'.format(
                        asset.symbol, humanize_number(amount), asset.name_fa,
                        humanize_number(int(base_amount))
                    ),
                    level=Notification.INFO,
                )
