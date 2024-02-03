from decimal import Decimal

from django.conf import settings
from django.db.models import Sum

from accounting.models import VaultItem, Vault, ReservedAsset
from accounts.models import Account
from financial.models import FiatWithdrawRequest
from ledger.models import Wallet, Prize, Asset
from ledger.utils.fields import PENDING
from ledger.utils.price import USDT_IRT
from ledger.utils.provider import get_provider_requester, BINANCE


class AssetOverview:
    def __init__(self, prices: dict):
        self.provider = get_provider_requester()
        self._binance_futures = self.provider.get_futures_info(BINANCE)

        wallets = Wallet.objects.filter(
            account__type=Account.ORDINARY
        ).exclude(
            market__in=(Wallet.VOUCHER, Wallet.DEBT)
        ).exclude(
            account__owned=True
        ).values('asset__symbol').annotate(amount=Sum('balance'))
        self.users_balances = {w['asset__symbol']: w['amount'] for w in wallets}

        self.prices = prices

        self.assets_map = {a.symbol: a for a in Asset.objects.all()}

        self.reserved_assets = dict(ReservedAsset.objects.values_list('coin', 'amount'))

    def get_binance_margin_ratio(self):
        if not self._binance_futures:
            return

        margin_balance = float(self._binance_futures['total_margin_balance'])
        initial_margin = float(self._binance_futures['total_initial_margin'])
        return margin_balance / max(initial_margin, 1e-10)

    def get_real_assets(self, coin: str):
        return VaultItem.objects.filter(coin=coin).aggregate(balance=Sum('balance'))['balance'] or 0

    def get_all_real_assets_value(self):
        return Vault.objects.aggregate(value=Sum('real_value'))['value'] or 0

    def get_reserved_assets_amount(self, coin: str):
        return self.reserved_assets.get(coin, 0)

    def get_total_reserved_assets_value(self):
        return ReservedAsset.objects.aggregate(value=Sum('value_usdt'))['value'] or 0

    def get_hedge_amount(self, coin: str):
        return self.get_real_assets(coin) - self.users_balances.get(coin, 0) - self.get_reserved_assets_amount(coin)

    def get_hedge_value(self, coin: str) -> Decimal:
        amount = Decimal(self.get_hedge_amount(coin))

        if not amount:
            return Decimal(0)

        price = self.prices.get(coin + Asset.USDT, 0)
        return amount * price

    def get_users_asset_amount(self, coin: str) -> Decimal:
        return self.users_balances.get(coin, 0)

    def get_users_asset_value(self, coin: str) -> Decimal:
        balance = self.get_users_asset_amount(coin)

        if not balance:
            return Decimal(0)

        price = self.prices.get(coin + Asset.USDT, 0)
        return balance * price

    def get_all_users_asset_value(self) -> Decimal:
        value = Decimal(0)

        for coin, balance in self.users_balances.items():
            value += self.get_users_asset_value(coin)

        pending_withdraws = FiatWithdrawRequest.objects.filter(
            status=PENDING
        ).aggregate(amount=Sum('amount'))['amount'] or 0

        return value - pending_withdraws / self.prices[USDT_IRT]

    def get_all_prize_value(self) -> Decimal:
        return Prize.objects.filter(
            redeemed=True
        ).aggregate(value=Sum('value'))['value'] or 0

    def get_total_hedge_value(self):
        return sum([
            abs(self.get_hedge_value(asset.symbol) or 0) for asset in Asset.live_objects.filter(hedge=True)
        ])

    def get_total_cumulative_hedge_value(self):
        return sum([
            self.get_hedge_value(asset.symbol) or 0 for asset in Asset.live_objects.filter(hedge=True)
        ])

    def get_exchange_assets_usdt(self):
        return self.get_all_real_assets_value() - self.get_all_users_asset_value()

    def get_margin_insurance_balance(self):
        return Asset.get(Asset.USDT).get_wallet(settings.MARGIN_INSURANCE_ACCOUNT).balance
