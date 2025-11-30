import csv
import datetime
import zoneinfo
from datetime import timedelta

import requests
from celery import shared_task
from decouple import config
from django.db.models import Sum, F, Value
from django.db.models.functions import TruncDate, Concat
from django.utils import timezone

from accounts.models import User
from accounts.utils.validation import gregorian_to_jalali_date, gregorian_to_jalali_datetime
from financial.models import Payment, FiatWithdrawRequest
from ledger.models import Asset
from ledger.utils.fields import DONE
from market.models import Trade


def send_accounting_report(file_path: str):
    f = open(file_path, 'rb')
    file_bytes = f.read()
    f.close()
    token = config('ACCOUNTING_TELEGRAM_TOKEN')
    chat_id = config('ACCOUNTING_TELEGRAM_CHAT_ID')
    document = (f.name, file_bytes)
    url = 'https://api.telegram.org/bot{token}/sendDocument'.format(token=token)

    resp = requests.post(url, params={'chat_id': chat_id}, files={'document': document}, timeout=10)
    return resp.json()


def create_trades(start: datetime.date, end: datetime.date, upload: bool = False):
    iran_tz = zoneinfo.ZoneInfo('Asia/Tehran')

    trades_query = Trade.objects.filter(
        created__range=(start, end),
        symbol__base_asset=Asset.get(Asset.IRT),
    ).exclude(trade_source=Trade.SYSTEM).exclude(gap_revenue=0).annotate(
        date=TruncDate('created', tzinfo=iran_tz)
    ).values('date', 'side').annotate(value=Sum(F('amount') * F('price')) * 10).order_by('date', 'side')

    trades = []

    for t in trades_query:
        trades.append({
            'value': t['value'],
            'date': str(gregorian_to_jalali_date(t['date'])),
            'side': t['side']
        })

    file_path = '/tmp/accounting/weekly_trades_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['date', 'side', 'value']
        t = csv.DictWriter(csv_file, fieldnames=header)
        t.writeheader()
        t.writerows(trades)

    if upload:
        send_accounting_report(file_path=file_path)

    return trades


def create_users_trades(start: datetime.date, end: datetime.date, upload: bool = False):
    trades = Trade.objects.filter(
        created__range=(start, end),
        symbol__base_asset=Asset.get(Asset.IRT),
        account__user__level__gt=User.LEVEL1,
    ).exclude(trade_source=Trade.SYSTEM).exclude(gap_revenue=0).annotate(
        user_id=F('account__user_id'),
        user_name=Concat('account__user__first_name', Value(' '), 'account__user__last_name'),
        user_national_code=F('account__user__national_code'),
    ).values('user_id', 'user_name', 'user_national_code', 'side').annotate(value=Sum(F('amount') * F('price')) * 10).order_by('user_id', 'side')

    file_path = '/tmp/accounting/weekly_users_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['user_id', 'user_name', 'user_national_code', 'side', 'value']
        t = csv.DictWriter(csv_file, fieldnames=header)
        t.writeheader()
        t.writerows(trades)

    if upload:
        send_accounting_report(file_path=file_path)

    return trades


def create_fiat_deposit(start: datetime.date, end: datetime.date, upload: bool = False):
    iran_tz = zoneinfo.ZoneInfo('Asia/Tehran')

    deposits_query = Payment.objects.filter(
        created__range=(start, end),
        status=DONE,
        paymentrequest__isnull=False,
    ).annotate(date=TruncDate('created', tzinfo=iran_tz)).values('date', 'paymentrequest__gateway__type').annotate(
        amount=Sum('payment_request__amount') * 10,
    ).order_by('date', 'paymentrequest__gateway__type')

    deposits = []

    for d in deposits_query:
        deposits.append({
            'gateway': d['paymentrequest__gateway__type'],
            'date': str(gregorian_to_jalali_date(d['date'])),
            'amount': d['amount']
        })

    file_path = '/tmp/accounting/weekly_deposit_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['date', 'gateway', 'amount']
        w = csv.DictWriter(csv_file, fieldnames=header)
        w.writeheader()
        w.writerows(deposits)

    if upload:
        send_accounting_report(file_path=file_path)

    return deposits


def create_fiat_withdraw(start: datetime.date, end: datetime.date, upload: bool = False):
    iran_tz = zoneinfo.ZoneInfo('Asia/Tehran')

    withdraws_query = FiatWithdrawRequest.objects.filter(
        created__range=(start, end),
        status=DONE,
    ).annotate(date=TruncDate('created', tzinfo=iran_tz)).values('date', 'withdraw_channel').annotate(
        amount=Sum('amount') * 10,
    ).order_by('date', 'withdraw_channel')

    withdraws = []

    for w in withdraws_query:
        withdraws.append({
            'gateway': w['withdraw_channel'],
            'date': str(gregorian_to_jalali_date(w['date'])),
            'amount': w['amount']
        })

    file_path = '/tmp/accounting/weekly_withdraw_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['date', 'gateway', 'amount']
        w = csv.DictWriter(csv_file, fieldnames=header)
        w.writeheader()
        w.writerows(withdraws)

    if upload:
        send_accounting_report(file_path=file_path)

    return withdraws


def create_fiat_deposit_details(start: datetime.date, end: datetime.date, upload: bool = False):
    payments = Payment.objects.filter(
        created__range=(start, end),
        status=DONE
    ).order_by('id').prefetch_related('paymentrequest__gateway', 'payment_request__bank_card__user')

    deposits = []

    for p in payments:
        user = p.user

        deposits.append({
            'id': p.id,
            'user_id': user.id,
            'user_name': user.get_full_name(),
            'user_national_code': user.national_code,
            'gateway': p.payment_request.gateway.type,
            'date': str(gregorian_to_jalali_datetime(p.created)),
            'amount': p.amount * 10
        })

    file_path = '/tmp/accounting/deposit_details_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['id', 'user_id', 'user_name', 'user_national_code', 'date', 'gateway', 'amount']
        w = csv.DictWriter(csv_file, fieldnames=header)
        w.writeheader()
        w.writerows(deposits)

    if upload:
        send_accounting_report(file_path=file_path)

    return deposits


def create_fiat_withdraw_details(start: datetime.date, end: datetime.date, upload: bool = False):
    withdraws = FiatWithdrawRequest.objects.filter(
        created__range=(start, end),
        status=DONE,
    ).order_by('id').prefetch_related('bank_account__user')

    withdraws_list = []

    for w in withdraws:
        user = w.bank_account.user

        withdraws_list.append({
            'id': w.id,
            'user_id': user.id,
            'user_name': user.get_full_name(),
            'user_national_code': user.national_code,
            'gateway': w.withdraw_channel,
            'date': str(gregorian_to_jalali_datetime(w.created)),
            'amount': w.amount * 10
        })

    file_path = '/tmp/accounting/withdraw_details_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['id', 'user_id', 'user_name', 'user_national_code', 'date', 'gateway', 'amount']
        w = csv.DictWriter(csv_file, fieldnames=header)
        w.writeheader()
        w.writerows(withdraws_list)

    if upload:
        send_accounting_report(file_path=file_path)

    return withdraws_list


def create_trades_details(start: datetime.date, end: datetime.date, upload: bool = False):
    trades = Trade.objects.filter(
        created__range=(start, end),
        symbol__base_asset=Asset.get(Asset.IRT),
    ).exclude(
        trade_source=Trade.SYSTEM
    ).exclude(
        gap_revenue=0
    ).order_by('id').prefetch_related('account__user', 'symbol__asset')

    trades_list = []

    for t in trades:
        user = t.account.user
        asset = t.symbol.asset

        trades_list.append({
            'id': t.id,
            'user_id': user.id,
            'user_name': user.get_full_name(),
            'user_national_code': user.national_code,
            'coin': asset.symbol,
            'amount': t.amount,
            'price': t.price,
            'value': t.price * t.amount * 10,
            'date': str(gregorian_to_jalali_datetime(t.created)),
            'side': t.side
        })

    file_path = '/tmp/accounting/trade_details_{}_{}.csv'.format(str(start), str(end))

    with open(file_path, 'w', newline="") as csv_file:
        header = ['id', 'user_id', 'user_name', 'user_national_code', 'date', 'value', 'side', 'coin', 'amount', 'price']
        t = csv.DictWriter(csv_file, fieldnames=header)
        t.writeheader()
        t.writerows(trades_list)

    if upload:
        send_accounting_report(file_path=file_path)

    return trades_list


@shared_task(queue='accounting')
def create_weekly_accounting_report(days: int = 7):
    end = timezone.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)

    create_fiat_deposit(start, end, upload=True)
    create_fiat_withdraw(start, end, upload=True)
    create_trades(start, end, upload=True)
    create_users_trades(start, end, upload=True)


