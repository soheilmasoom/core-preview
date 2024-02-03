from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from accounting.models import Vault, VaultItem
from financial.models import FiatWithdrawRequest
from ledger.models import Transfer, OTCTrade, Asset, SystemSnapshot, NetworkAsset
from ledger.requester.internal_assets_requester import get_hot_wallet_balances
from ledger.utils.fields import PENDING, PROCESS
from ledger.utils.precision import get_presentation_amount


@dataclass
class Status:
    OK, WARNING, ERROR = 'ok', 'warning', 'error'

    type: str
    count: int = 0
    description: str = ''

    def __str__(self):
        if self.type == self.OK:
            return self.OK.upper()

        return f'{self.type.upper()} {self.count}'

    @classmethod
    def from_alerts(cls, status_type: str, alerts: list) -> 'Status':
        if not alerts:
            return Status(Status.OK)

        return Status(
            type=status_type,
            description='; '.join(map(str, alerts[:5])),
            count=len(alerts)
        )

    @property
    def ok(self):
        return self.type == self.OK


class BaseAlertHandler:
    NAME = None
    ALERTS = (Status.WARNING, Status.ERROR)
    HELP = 'threshold'

    def __init__(self, warning_threshold: Decimal, error_threshold: Decimal):
        self.warning_threshold = warning_threshold
        self.error_threshold = error_threshold

    def get_status(self) -> Status:
        if Status.ERROR in self.ALERTS:
            status = Status.from_alerts(Status.ERROR, self.get_alerting(self.error_threshold))

            if not status.ok:
                return status

        if Status.WARNING in self.ALERTS:
            status = Status.from_alerts(Status.WARNING, self.get_alerting(self.warning_threshold))

            if not status.ok:
                return status

        return Status(Status.OK)

    def get_alerting(self, threshold: Decimal) -> list:
        raise NotImplemented


class UnhandledCryptoWithdrawAlert(BaseAlertHandler):
    NAME = 'unhandled_crypto_withdraw'
    HELP = 'time passed from now in minutes'

    def get_alerting(self, threshold: Decimal):
        return Transfer.objects.filter(
            deposit=False,
            accepted_datetime__isnull=False,
            status__in=[PROCESS, PENDING],
            trx_hash__isnull=True,
            accepted_datetime__lt=timezone.now() - timedelta(minutes=int(threshold)),
        )


class CryptoLongConfirmationAlert(BaseAlertHandler):
    NAME = 'crypto_long_confirmation'
    HELP = 'multiplier to Network\'s expected_confirmation_minutes'

    def get_alerting(self, threshold: Decimal):
        transfers = Transfer.objects.filter(
            status=PENDING,
            trx_hash__isnull=False,
            accepted_datetime__isnull=False,
        ).prefetch_related('network')

        now = timezone.now()

        return list(filter(
            lambda t: t.accepted_datetime < now - timedelta(minutes=int(threshold * t.network.expected_confirmation_minutes)),
            transfers
        ))


class UnhandledFiatWithdrawAlert(BaseAlertHandler):
    NAME = 'unhandled_fiat_withdraw'
    HELP = 'time passed from now in minutes'

    def get_alerting(self, threshold: Decimal):
        return FiatWithdrawRequest.objects.filter(
            status__in=[PROCESS],
            created__lt=timezone.now() - timedelta(minutes=int(threshold)),
        )


class LongPendingFiatWithdrawAlert(BaseAlertHandler):
    NAME = 'long_pending_fiat_withdraw'
    HELP = 'time passed from now in minutes'

    def get_alerting(self, threshold: Decimal):
        return FiatWithdrawRequest.objects.filter(
            status__in=[PENDING],
            created__lt=timezone.now() - timedelta(minutes=int(threshold)),
        )


class CanceledOTCAlert(BaseAlertHandler):
    NAME = 'canceled_otc'
    HELP = 'time passed from now in minutes'

    def get_alerting(self, threshold: Decimal) -> list:
        return OTCTrade.objects.filter(
            created__gte=timezone.now() - timedelta(minutes=int(threshold)),
            status=OTCTrade.CANCELED,
        )


class AssetHedgeAlert(BaseAlertHandler):
    NAME = 'asset_hedge'
    HELP = 'max asset hedge'

    def get_alerting(self, threshold: Decimal) -> list:
        assets = Asset.live_objects.filter(hedge=True).annotate(
            hedge_value_abs=F('assetsnapshot__hedge_value_abs'),
        ).filter(hedge_value_abs__gte=threshold)

        return [f'{a.symbol}: {int(a.hedge_value_abs)}$' for a in assets]


class TotalHedgeAlert(BaseAlertHandler):
    NAME = 'total_hedge'
    HELP = 'max system hedge'

    def get_alerting(self, threshold: Decimal) -> list:
        snapshot = SystemSnapshot.objects.last()  # type: SystemSnapshot
        hedge = snapshot and snapshot.hedge  # type: Decimal

        if hedge is not None and abs(hedge) > threshold:
            return [f'system: {int(hedge)}']


class FiatHedgeAlert(BaseAlertHandler):
    NAME = 'fiat_hedge'
    HELP = 'max fiat hedge'

    def get_alerting(self, threshold: Decimal) -> list:
        assets = Asset.live_objects.filter(symbol=Asset.IRT).annotate(
            hedge_value_abs=F('assetsnapshot__hedge_value_abs'),
        ).filter(hedge_value_abs__gte=threshold)

        return [f'{a.symbol}: {int(a.hedge_value_abs)}$' for a in assets]


class RiskyMarginRatioAlert(BaseAlertHandler):
    NAME = 'risky_margin_ratio'
    HELP = 'min margin ratio'

    def get_alerting(self, threshold: Decimal) -> list:
        snapshot = SystemSnapshot.objects.last()  # type: SystemSnapshot
        margin_ratio = snapshot and snapshot.binance_margin_ratio  # type: Decimal

        if margin_ratio is not None and abs(margin_ratio) < threshold:
            return [f'system: {round(margin_ratio, 2)}']


class VaultLowBaseBalanceAlert(BaseAlertHandler):
    NAME = 'vault_low_base_balance'
    HELP = 'multiplier to VaultItem\'s expected_min_balance'

    def get_alerting(self, threshold: Decimal) -> list:
        vault_items = VaultItem.objects.filter(
            expected_min_balance__isnull=False,
            balance__lt=F('expected_min_balance') * threshold
        )

        return [
            f'{vi} ({int(vi.balance)} < {int(vi.expected_min_balance * threshold)})' for vi in vault_items
        ]


class VaultHighBalanceAlert(BaseAlertHandler):
    NAME = 'vault_high_balance'
    HELP = 'multiplier to Vault\'s expected_max_value (in usdt)'

    def get_alerting(self, threshold: Decimal) -> list:
        vaults = Vault.objects.filter(
            expected_max_value__isnull=False,
            real_value__gt=F('expected_max_value') * threshold
        )

        return [
            f'{v} ({int(v.real_value)} > {int(v.expected_max_value * threshold)})' for v in vaults
        ]


class HotWalletLowBalanceAlert(BaseAlertHandler):
    NAME = 'hot_wallet_low_balance'
    HELP = 'multiplier to NetworkAsset\'s expected_hw_balance'

    def get_alerting(self, threshold: Decimal) -> list:
        hw_balances = get_hot_wallet_balances()

        network_assets = NetworkAsset.objects.filter(expected_hw_balance__gt=0).prefetch_related('asset', 'network')

        network_assets = list(filter(
            lambda ns: hw_balances.get((ns.asset.symbol, ns.network.symbol), 0) < ns.expected_hw_balance * threshold,
            network_assets
        ))

        return [
            f'{ns} ({get_presentation_amount(hw_balances.get((ns.asset.symbol, ns.network.symbol), 0))} < {get_presentation_amount(ns.expected_hw_balance * threshold)})'
            for ns in network_assets
        ]
