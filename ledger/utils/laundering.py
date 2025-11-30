from decimal import Decimal

from accounts.models import User
from financial.models import Payment, FiatWithdrawRequest
from ledger.models import Wallet, Asset
from ledger.utils.external_price import SELL, BUY
from ledger.utils.fields import DONE
from ledger.utils.price import get_price


def get_user_irt_net_deposit(user: User) -> int:

    irt_deposits = Payment.objects.filter(
        user=user,
        status=DONE
    ).order_by('created').values_list('created', 'amount')

    irt_withdraws = FiatWithdrawRequest.objects.filter(
        bank_account__user=user,
        status=DONE
    ).order_by('created').values_list('created', 'amount', 'fee_amount')

    net_irt_transfers = list(irt_deposits) + [(created, -amount - fee) for (created, amount, fee) in irt_withdraws]
    net_irt_transfers.sort(key=lambda x: x[0])

    irt_values = list(map(lambda x: x[1], net_irt_transfers))

    net_deposit = 0

    for value in irt_values:
        net_deposit += value

        if net_deposit < 0:
            net_deposit = 0

    return net_deposit
    
    
def check_withdraw_laundering(wallet: Wallet, amount: Decimal) -> bool:
    user = wallet.account.user

    if user.level >= User.LEVEL3:
        return True

    net_irt_deposit = get_user_irt_net_deposit(user)

    if net_irt_deposit <= 100000:
        return True

    total_irt_value = wallet.account.get_total_balance_irt(side=SELL)

    price = get_price(wallet.asset.symbol + Asset.IRT, side=BUY, allow_stale=True)

    return amount * price <= total_irt_value - net_irt_deposit
