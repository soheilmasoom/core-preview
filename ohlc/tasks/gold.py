from datetime import timedelta

from celery import shared_task
from django.db.models import Q, Min, Max, Avg
from django.utils import timezone
from decimal import Decimal
from django.db import transaction

from ledger.models import Asset
from ledger.utils.external_price import BUY
from ledger.utils.price import get_prices
from ohlc.models import Candle


@shared_task
def fetch_and_store_gold_candles():
    """
    Fetches prices and stores 1-minute candles.
    Important: We align the timestamp to the start of each minute
    to ensure consistent candle boundaries.
    """

    gold_asset = Asset.objects.filter(
        Q(symbol__startswith='XAU') | Q(symbol__startswith='XAUM'),
        enable=True
    ).first()

    symbol = f"{gold_asset.symbol}IRT"
    now = timezone.now()
    aligned_time = now.replace(second=0, microsecond=0)

    try:
        with transaction.atomic():
            buy_prices = get_prices([symbol], side=BUY, allow_stale=False)

            if symbol not in buy_prices:
                return

            price = buy_prices[symbol]

            Candle.objects.create(
                symbol=symbol,
                timestamp=aligned_time,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal('1')
            )
    except Exception as e:
        print(f"Error in fetch_and_store_candles: {str(e)}")
        raise


@shared_task
def aggregate_materialized_candles():
    """
    Aggregates 1-minute candles into larger timeframes (15min, 1h, 4h, 1d)
    and stores in MaterializedCandle.
    """
    from ohlc.models import Candle, MaterializedCandle
    from ledger.models import Asset

    gold_asset = Asset.objects.filter(
        Q(symbol__startswith='XAU') | Q(symbol__startswith='XAUM'),
        enable=True
    ).first()

    symbol = f"{gold_asset.symbol}IRT"
    now = timezone.now()

    timeframes = {
        '15min': 15,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }

    try:
        with transaction.atomic():
            for timeframe, minutes in timeframes.items():
                start_time = now - timedelta(minutes=minutes)

                start_time = start_time.replace(
                    minute=(start_time.minute // minutes) * minutes,
                    second=0,
                    microsecond=0
                )

                interval_candles = Candle.objects.filter(
                    symbol=symbol,
                    timestamp__gte=start_time,
                    timestamp__lt=now
                )

                if interval_candles.exists():
                    agg = interval_candles.aggregate(
                        open_price=Min('open'),
                        high_price=Max('high'),
                        low_price=Min('low'),
                        close_price=Max('close'),
                        volume_sum=Avg('volume')
                    )

                    MaterializedCandle.objects.update_or_create(
                        symbol=symbol,
                        timestamp=start_time,
                        timeframe=timeframe,
                        defaults={
                            'open': agg['open_price'],
                            'high': agg['high_price'],
                            'low': agg['low_price'],
                            'close': agg['close_price'],
                            'volume': agg['volume_sum']
                        }
                    )
    except Exception as e:
        print(f"Error in aggregate_materialized_candles: {str(e)}")
        raise
