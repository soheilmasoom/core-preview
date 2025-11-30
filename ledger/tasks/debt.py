from celery import shared_task

from ledger.fix.revert_trade import clear_debt
from ledger.models import Wallet


@shared_task(queue='celery')
def auto_clear_debts():
    debt_wallets = Wallet.objects.filter(market=Wallet.DEBT, balance__lt=0)

    for debt_wallet in debt_wallets:
        spot_wallet = Wallet.objects.filter(
            account=debt_wallet.account,
            asset=debt_wallet.asset,
            market=Wallet.SPOT,
            variant__isnull=True,
            balance__gt=0,
        ).first()

        if spot_wallet:
            clear_debt(spot_wallet, debt_wallet)
