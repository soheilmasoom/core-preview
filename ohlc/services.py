import logging
from decimal import Decimal
from typing import List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.timezone import datetime

from ledger.utils.external_price import SELL
from ledger.utils.price import get_prices
from ohlc.models import Candle

logger = logging.getLogger(__name__)


def create_one_minute_candles(
        symbols_list: List[str],
        timestamp: Optional[datetime] = None,
        batch_size: int = 100
) -> List[Candle]:
    if not symbols_list:
        raise ValueError("symbols_list cannot be empty")
    # Use provided timestamp or align current time to minute
    aligned_time = (timestamp or timezone.now()).replace(second=0, microsecond=0)
    original_symbols_list = symbols_list[:]

    try:
        all_prices = get_prices(symbols_list, side=SELL, allow_stale=False)
        candles_to_create = []

        for symbol in original_symbols_list:
            if symbol not in all_prices:
                logger.warning(f"Failed to get price for symbol: {symbol}",
                               extra={'timestamp': aligned_time})
                all_prices[symbol] = Decimal('0')
            price = all_prices[symbol]
            candles_to_create.append(Candle(
                symbol=symbol,
                timestamp=aligned_time,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal('1')
            ))

        with transaction.atomic():
            if candles_to_create:
                return Candle.objects.bulk_create(
                    candles_to_create,
                    batch_size=batch_size,
                    ignore_conflicts=True
                )
            return []

    except Exception as e:
        logger.error(f"Failed to create candles: {str(e)}",
                     extra={
                         'symbols_count': len(symbols_list),
                         'timestamp': aligned_time
                     })
        raise
