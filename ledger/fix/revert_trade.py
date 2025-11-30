from uuid import uuid4

from accounts.models import User
from ledger.models import OTCTrade, Wallet, Trx
from ledger.utils.wallet_pipeline import WalletPipeline


def revert_otc_trades(user: User, min_otc_trade_id: int, max_otc_trade_id: int):
    trades = OTCTrade.objects.filter(
        otc_request__account__user=user,
        status=OTCTrade.DONE,
        id__range=(min_otc_trade_id, max_otc_trade_id),
    ).order_by('-id')

    for t in trades:
        print('reverting %s' % t)
        t.revert()

    clear_user_debts(user)


def clear_user_debts(user: User):
    account = user.get_account()

    spot_wallets_list = Wallet.objects.filter(account=account, market=Wallet.SPOT).exclude(balance=0)
    spot_dict = {w.asset: w for w in spot_wallets_list}
    debt_wallets_list = Wallet.objects.filter(account=account, market=Wallet.DEBT).exclude(balance=0)
    debt_dict = {w.asset: w for w in debt_wallets_list}

    to_clear_assets = set(spot_dict) & set(debt_dict)

    for asset in to_clear_assets:
        sw = spot_dict[asset]
        dw = debt_dict[asset]

        clear_debt(sw, dw)


def clear_debt(spot_wallet: Wallet, debt_wallet: Wallet):
    amount = min(spot_wallet.get_free(), -debt_wallet.balance)

    if amount > 0:
        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=spot_wallet,
                receiver=debt_wallet,
                amount=amount,
                scope=Trx.DEBT_CLEAR,
                group_id=uuid4()
            )
