from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounting.models import TradeRevenue
from analytics.models import ActiveTrader, Symbol
from analytics.utils.event import trigger_users_event, trigger_transfer_event, trigger_fiat_transfer_event, \
    trigger_payment_event, trigger_trade_event, trigger_otc_trade, trigger_login_event, trigger_prize_event, \
    trigger_stake_event, trigger_traffic_source, trigger_wallet_event, trigger_transaction_event
from analytics.utils.price_collect import collect_symbol


@shared_task(queue='history')
def create_analytics(now=None):
    if not now:
        now = timezone.now()

    for period in ActiveTrader.PERIODS:
        start = now - timedelta(days=period)

        accounts = set(TradeRevenue.objects.filter(
            created__range=(start, now)
        ).values_list('account', flat=True).distinct())

        old_accounts = set(TradeRevenue.objects.filter(
            created__range=(start - timedelta(days=1), now - timedelta(days=1))
        ).values_list('account', flat=True).distinct())

        ActiveTrader.objects.get_or_create(
            created=now,
            period=period,
            defaults={
                'active': len(accounts),
                'churn': len(old_accounts - accounts),
                'new': len(accounts - old_accounts),
            }
        )


@shared_task(queue='history')
def trigger_kafka_event():
    trigger_users_event()
    trigger_transfer_event()
    trigger_fiat_transfer_event()
    trigger_payment_event()
    trigger_trade_event()
    trigger_otc_trade()
    trigger_login_event()
    trigger_prize_event()
    trigger_stake_event()
    trigger_traffic_source()
    trigger_wallet_event()
    trigger_transaction_event()


@shared_task(queue='history')
def collect_symbol_prices():
    for symbol in Symbol.objects.filter(auto_collect=True):
        collect_symbol(symbol)
