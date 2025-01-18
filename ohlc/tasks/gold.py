from celery import shared_task
from django.db.models import Q

from ledger.models import Asset
from ohlc.models import Candle
from ohlc.services import create_one_minute_candles


@shared_task
def refresh_materialized_views():
    Candle.update_higher_timeframes()


@shared_task
def fetch_and_store_gold_candles():
    gold_asset = Asset.objects.filter(
        Q(symbol__startswith='XAU') | Q(symbol__startswith='XAUM'),
        enable=True
    ).first()

    symbol = f"{gold_asset.symbol}IRT"
    create_one_minute_candles([symbol])
