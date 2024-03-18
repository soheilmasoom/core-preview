from typing import List

from django.db.models import Q

from accounting.models import Account
from ledger.models import Trx
from ledger.utils.precision import get_presentation_amount


def export_transactions(account: Account) -> List[dict]:
    transactions = Trx.objects.filter(Q(sender__account=account) | Q(receiver__account=account)).distinct().values(
        'id', 'created', 'sender__account', 'receiver__account', 'amount', 'sender__asset__symbol', 'scope'
    ).order_by('id')

    response = []

    for trx in transactions:
        if trx['sender__account'] == account.id:
            response.append({
                'id': trx['id'],
                'created': trx['created'].strftime('%Y-%m-%d %H:%M:%S'),
                'coin': trx['sender__asset__symbol'],
                'amount': get_presentation_amount(-trx['amount']),
                'scope': Trx.SCOPES_VERBOSE[trx['scope']]
            })

        if trx['receiver__account'] == account.id:
            response.append({
                'id': trx['id'],
                'created': trx['created'].strftime('%Y-%m-%dT%H:%M:%S'),
                'coin': trx['sender__asset__symbol'],
                'amount': get_presentation_amount(trx['amount']),
                'scope': Trx.SCOPES_VERBOSE[trx['scope']]
            })

    return response
