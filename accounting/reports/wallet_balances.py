import csv
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from accounting.tasks.weekly_reports import send_accounting_report
from accounts.models import Account, User
from ledger.models import Asset, Trx


def build_user_wallets_balance(date, upload: bool = False):
    irt = Asset.get(Asset.IRT)

    trx_list = Trx.objects.filter(
        created__lte=date,
        sender__asset=irt
    ).values('sender__account', 'receiver__account').annotate(amount=Sum('amount'))

    balance_map = defaultdict(Decimal)

    for t in trx_list:
        balance_map[t['sender__account']] -= t['amount']
        balance_map[t['receiver__account']] += t['amount']

    users = User.objects.filter(account__type=Account.SYSTEM, account__id__in=balance_map)

    wallets_info = []

    for user in users:
        wallets_info.append({
            'user_id': user.id,
            'user_name': user.get_full_name(),
            'user_national_code': user.national_code,
            'balance': balance_map[user.get_account().id] * 10
        })

    file_path = '/tmp/accounting/wallets_{}.csv'.format(str(date))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['id', 'user_id', 'user_name', 'user_national_code', 'balance']
        t = csv.DictWriter(csv_file, fieldnames=header)
        t.writeheader()
        t.writerows(wallets_info)

    if upload:
        send_accounting_report(file_path=file_path)



