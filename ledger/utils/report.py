from typing import List

from django.db.models import Q

from accounting.models import Account
from ledger.models import Trx, Wallet
from ledger.utils.precision import get_presentation_amount


def export_transactions(account: Account) -> List[dict]:
    transactions = Trx.objects.filter(
        Q(sender__account=account) | Q(receiver__account=account)
    ).exclude(receiver__market=Wallet.VOUCHER).distinct().values(
        'id', 'created', 'sender__account', 'sender__market', 'receiver__account', 'receiver__market', 'amount',
        'sender__asset__symbol', 'scope'
    ).order_by('id')

    response = []

    for trx in transactions:
        if trx['sender__account'] == account.id:
            response.append({
                'id': trx['id'],
                'created': trx['created'].strftime('%Y-%m-%d %H:%M:%S'),
                'coin': trx['sender__asset__symbol'],
                'amount': get_presentation_amount(-trx['amount']),
                'scope': Trx.SCOPES_VERBOSE[trx['scope']],
                'wallet_type': trx['sender__market'],
            })

        if trx['receiver__account'] == account.id:
            response.append({
                'id': trx['id'],
                'created': trx['created'].strftime('%Y-%m-%d %H:%M:%S'),
                'coin': trx['sender__asset__symbol'],
                'amount': get_presentation_amount(trx['amount']),
                'scope': Trx.SCOPES_VERBOSE[trx['scope']],
                'wallet_type': trx['receiver__market'],
            })

    return response
