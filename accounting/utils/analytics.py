from datetime import datetime

from django.db.models import Sum, F, Q

from accounting.models import TradeRevenue
from accounts.models import User
from financial.models import Payment
from ledger.models import Transfer
from ledger.utils.fields import DONE


def produce_users_analytics(user_ids: list, start: datetime = None, end: datetime = None):
    users = User.objects.filter(id__in=user_ids)
    payments = Payment.objects.filter(
        user_id__in=user_ids,
        status=DONE
    )

    transfers = Transfer.objects.filter(wallet__account__user_id__in=users)
    trades = TradeRevenue.objects.filter(account__user_id__in=users)

    if start:
        payments = payments.filter(created__gte=start)
        transfers = transfers.filter(created__gte=start)
        trades = trades.filter(created__gte=start)

    if end:
        payments = payments.filter(created__lte=end)
        transfers = transfers.filter(created__lte=end)
        trades = trades.filter(created__lte=end)

    with_deposit_users = set(payments.values_list('user_id', flat=True))
    with_deposit_users |= set(transfers.values_list('wallet__account__user_id', flat=True))

    crypto_deposit_volume = transfers.aggregate(value=Sum('irt_value'))['value'] or 0
    fiat_deposit_volume = payments.aggregate(value=Sum('amount'))['value'] or 0

    data = {
        'users': len(user_ids),
        'verified': users.filter(level__gt=User.LEVEL1).count(),
        'deposited': len(with_deposit_users),
        'deposit_value': fiat_deposit_volume + crypto_deposit_volume,
        'traders': len(set(trades.values_list('account__user_id', flat=True))),
        'trade_volume': trades.aggregate(value=Sum('value'))['value'] or 0,
        'trade_revenue': trades.aggregate(value=Sum(F('gap_revenue') + F('fee_revenue'))
        )['value'] or 0,
    }

    data.update({
        'verified_conv': round(float(data['verified'] * 100) / data['users'], 2),
        'deposited_conv': round(float(data['deposited'] * 100) / data['users'], 2),
        'trader_conv': round(float(data['traders'] * 100) / data['users'], 2),
        'deposit_value_per_user': round(float(data['deposit_value']) / data['users'], 2),
        'trade_volume_per_user': round(float(data['trade_volume']) / data['users'], 2),
        'trade_revenue_per_user': round(float(data['trade_revenue']) / data['users'], 2),
    })

    return data
