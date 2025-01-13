import dataclasses
from datetime import timedelta, datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import User, Account, Notification, SmsNotification, SystemConfig
from accounts.utils.validation import gregorian_to_jalali_date
from ledger.models import Asset, Wallet, Trx
from ledger.utils.external_price import BUY
from ledger.utils.fields import get_status_field, CANCELED, DONE, PENDING, get_group_id_field, REFUND
from ledger.utils.precision import humanize_number
from ledger.utils.price import get_price
from ledger.utils.revert import revert_trx_group
from ledger.utils.wallet_pipeline import WalletPipeline


@dataclasses.dataclass
class DelistInfo:
    asset_amounts: Decimal
    base_amounts: Decimal


ALARM_SMS_CONTENT = """
کاربر گرامی {brand}،
به منظور حفظ امنیت و کاهش ریسک، توکن {coin} در تاریخ {delist_at} از {brand} حذف خواهد شد. لطفا تا قبل از 
آن زمان نسبت به فروش یا برداشت این توکن اقدام نمایید.
"""

ALARM_SMS_CONTENT_NO_WITHDRAW = """
کاربر گرامی {brand}،
به منظور حفظ امنیت و کاهش ریسک، توکن {coin} در تاریخ {delist_at} از {brand} حذف خواهد شد. لطفا تا قبل از 
آن زمان نسبت به فروش این توکن اقدام نمایید.
"""

ALARM_NOTIF_CONTENT = """
به منظور حفظ امنیت و کاهش ریسک، توکن {coin} در تاریخ {delist_at} از {brand} حذف خواهد شد. لطفا تا قبل از آن، نسبت به فروش یا برداشت این توکن اقدام نمایید.
"""

ALARM_NOTIF_CONTENT_NO_WITHDRAW = """
به منظور حفظ امنیت و کاهش ریسک، توکن {coin} در تاریخ {delist_at} از {brand} حذف خواهد شد. لطفا تا قبل از آن، نسبت به فروش این توکن اقدام نمایید.
"""


def default_delist_at() -> datetime:
    delist_at = timezone.now().astimezone() + timedelta(days=7)
    return delist_at.replace(hour=9, minute=0, second=0, microsecond=0)


class TokenDelist(models.Model):
    created = models.DateTimeField(auto_now=True)
    delist_at = models.DateTimeField(default=default_delist_at)

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    status = get_status_field(default=PENDING)

    testers = models.ManyToManyField(User, limit_choices_to={'is_staff': True}, blank=True)
    group_id = get_group_id_field(unique=True)

    can_withdraw = models.BooleanField(default=True, help_text='Changes notification texts')

    def get_alarm_notif_content(self):
        template = ALARM_NOTIF_CONTENT if self.can_withdraw else ALARM_NOTIF_CONTENT_NO_WITHDRAW

        coin = self.asset.symbol
        jalali_date = str(gregorian_to_jalali_date(self.delist_at.astimezone())).replace('-', '/')

        return template.strip().format(
            coin=coin,
            delist_at=str(jalali_date),
            brand=settings.BRAND
        )

    def get_alarm_sms_content(self):
        template = ALARM_SMS_CONTENT if self.can_withdraw else ALARM_SMS_CONTENT_NO_WITHDRAW

        coin = self.asset.symbol
        jalali_date = str(gregorian_to_jalali_date(self.delist_at.astimezone())).replace('-', '/')

        return template.strip().format(
            coin=coin,
            delist_at=str(jalali_date),
            brand=settings.BRAND
        )

    def clean(self):
        if hasattr(self, 'asset'):
            if self.asset.otc_status == Asset.ACTIVE:
                raise ValidationError('Asset should not be active!')

            if not self.asset.enable:
                raise ValidationError('Asset should be enable!')

    def alarm_delist(self):
        wallets = self.get_candidate_wallets()

        users = User.objects.filter(
            id__in=wallets.values_list('account__user', flat=True).distinct()
        )

        price = get_price(self.asset.symbol + Asset.IRT, side=BUY)
        config = SystemConfig.get_system_config()

        to_sms_wallets = wallets.filter(balance__gte=config.min_otc_irt / price)
        to_sms_users = User.objects.filter(
            id__in=to_sms_wallets.values_list('account__user', flat=True).distinct()
        )

        coin = self.asset.symbol

        alarm_notif_content = self.get_alarm_notif_content()
        alarm_sms_content = self.get_alarm_sms_content()

        with transaction.atomic():
            for user in users:
                Notification.send(
                    recipient=user,
                    group_id=self.group_id,
                    title=f'حذف توکن {coin}',
                    message=alarm_notif_content
                )

            for user in to_sms_users:
                SmsNotification.objects.get_or_create(
                    recipient=user,
                    group_id=self.group_id,
                    defaults={
                        'content': alarm_sms_content
                    }
                )

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
            self.asset.save(update_fields=['enable'])

            delist.status = DONE
            delist.save(update_fields=['status'])

    def revert(self):
        with WalletPipeline() as pipeline:
            rebrand = TokenDelist.objects.filter(id=self.id, status=DONE).select_for_update().first()

            if not rebrand:
                return

            revert_trx_group(pipeline, self.group_id)

            Notification.objects.filter(group_id=self.group_id).delete()

            rebrand.status = REFUND
            rebrand.save(update_fields=['status'])

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
                base_amounts=humanize_number(amount_sum * price) if price else None
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
                    # group_id=self.group_id
                )
