from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict

from accounts.models import Account
from ledger.models import Wallet, Asset
from ledger.utils.price import get_last_price

TRANSFER_OUT_BLOCK_ML = Decimal('2')
BORROW_BLOCK_ML = Decimal('1.5')  # leverage = 3
MARGIN_CALL_ML_ALERTING_RESOLVE_THRESHOLD = Decimal('1.3')
MARGIN_CALL_ML_THRESHOLD = Decimal('1.22')
LIQUIDATION_ML_THRESHOLD = Decimal('1.15')


@dataclass
class MarginInfo:
    total_debt: Decimal
    total_assets: Decimal

    @classmethod
    def get(cls, account: Account) -> 'MarginInfo':
        wallets = Wallet.objects.filter(
            account=account,
            market__in=[Wallet.MARGIN, Wallet.LOAN]
        ).exclude(asset__symbol=Asset.IRT).prefetch_related('asset', 'account')

        total_assets = Decimal()
        total_debt = Decimal()

        for wallet in wallets:
            price = get_last_price(wallet.asset.symbol + Asset.USDT) or 0

            if wallet.market == Wallet.MARGIN:
                balance = wallet.balance * price
                total_assets += balance
            else:
                balance = wallet.balance * price
                total_debt += balance

        return MarginInfo(
            total_debt=-total_debt,
            total_assets=total_assets
        )

    def get_margin_level(self) -> Decimal:
        return get_margin_level(self.total_assets, self.total_debt)

    def get_total_equity(self):
        return self.total_assets - self.total_debt

    def get_max_borrowable(self) -> Decimal:
        return (self.total_assets - BORROW_BLOCK_ML * self.total_debt) / (BORROW_BLOCK_ML - 1)

    def get_max_transferable(self) -> Decimal:
        return self.total_assets - TRANSFER_OUT_BLOCK_ML * self.total_debt

    def get_liquidation_amount(self) -> Decimal:
        return -self.get_max_borrowable()


def get_margin_level(total_assets: Decimal, total_debt: Decimal):
    if total_debt <= 0:
        return Decimal(999)
    else:
        return total_assets / total_debt


def get_bulk_margin_info(accounts: List[Account]) -> Dict[Account, MarginInfo]:
    mapping = {}

    wallets = Wallet.objects.filter(
        account__in=accounts,
        market__in=[Wallet.MARGIN, Wallet.LOAN]
    ).exclude(asset__symbol=Asset.IRT).prefetch_related('asset', 'account')

    total_assets = defaultdict(Decimal)
    total_debt = defaultdict(Decimal)

    for wallet in wallets:
        price = get_last_price(wallet.asset.symbol + Asset.USDT) or 0 or 0

        if wallet.market == Wallet.MARGIN:
            total_assets[wallet.account_id] += wallet.balance * price
        else:
            total_debt[wallet.account_id] += wallet.balance * price

    for account in accounts:
        mapping[account] = MarginInfo(
            total_debt=-total_debt[account.id],
            total_assets=total_assets[account.id]
        )

    return mapping
