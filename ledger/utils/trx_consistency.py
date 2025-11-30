import logging
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum

from accounts.models import Account
from ledger.models import Trx, Wallet, BalanceLock

logger = logging.getLogger(__name__)


def check_account_consistency(account: Account):
    received = Trx.objects.filter(
        receiver__account=account,
    ).values('receiver').annotate(amount=Sum('amount')).values_list('receiver', 'amount')

    sent = Trx.objects.filter(
        sender__account=account,
    ).values('sender').annotate(amount=Sum('amount')).values_list('sender', 'amount')

    balances = defaultdict(Decimal)

    for wallet_id, amount in received:
        balances[wallet_id] += amount

    for wallet_id, amount in sent:
        balances[wallet_id] -= amount

    for wallet in Wallet.objects.filter(account=account):
        if wallet.balance != balances.get(wallet.id, 0):
            logger.info('balance mismatch for wallet %s: %f != %f' % (wallet.id, wallet.balance, balances.get(wallet.id, 0)))

    if account.is_ordinary_user():
        locked = BalanceLock.objects.filter(wallet__account=account, freed=False).values('wallet').annotate(
            amount=Sum('amount'))
        locked_dict = {}

        for l in locked:
            locked_dict[l['wallet']] = l['amount']

        for wallet in Wallet.objects.filter(account=account):
            if wallet.locked != locked_dict.get(wallet.id, 0):
                logger.info('locked mismatch for wallet %s: %f != %f' % (wallet.id, wallet.locked, locked_dict.get(wallet.id, 0)))


def check_all_accounts_consistency():
    for account in Account.objects.filter(type=Account.ORDINARY):
        check_account_consistency(account)


def check_overall_consistency():
    received = Trx.objects.values('receiver', 'receiver__market').annotate(amount=Sum('amount'))
    sent = Trx.objects.values('sender', 'sender__market').annotate(amount=Sum('amount'))

    received_dict = {}
    sent_dict = {}

    for r in received:
        received_dict[(r['receiver'], r['receiver__market'])] = r['amount']

    for s in sent:
        sent_dict[(s['sender'], s['sender__market'])] = s['amount']

    locked = BalanceLock.objects.filter(freed=False).values('wallet', 'wallet__market').annotate(amount=Sum('amount'))
    locked_dict = {}

    for l in locked:
        locked_dict[(l['wallet'], l['wallet__market'])] = l['amount']

    for w in Wallet.objects.all().prefetch_related('account'):
        key = (w.id, w.market)
        balance = received_dict.get(key, 0) - sent_dict.get(key, 0)
        locked = locked_dict.get(key, 0)
        check_balance = w.account.type is None

        if check_balance and w.market != Wallet.LOAN:
            if balance < 0:
                logger.info("%s (%s): negative balance (%f)" % (w, w.id, balance))

            if locked > balance:
                logger.info("%s (%s): locked (%f) > balance (%f)" % (w, w.id, locked, balance))


def get_wallet_trx_balance(wallet: Wallet):
    trx_history = Trx.objects.filter(Q(sender=wallet) | Q(receiver=wallet))
    balance = 0
    for trx in trx_history:
        if trx.sender == wallet:
            balance -= trx.amount
        if trx.receiver == wallet:
            balance += trx.amount
    return balance
