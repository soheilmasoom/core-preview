from datetime import timedelta
from typing import List

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from _base import settings
from ledger.models import Asset
from ledger.utils.external_price import fetch_external_price_by_symbol, SELL
from ledger.utils.provider import get_provider_requester
from ohlc.models import Ohlc1D, Ohlc1H


@shared_task(queue='celery')
def populate_coins_info():
    fetch_key = 'coins_info_fetching'

    if cache.get(fetch_key):
        print('updating coins info ignored')
        return

    cache.set(fetch_key, 1, 60)
    if settings.EXCHANGE_TYPE.is_crypto:
        coins_info = get_provider_requester().get_coins_info()
    else:
        coins_info = get_coins_info_from_ohlc()

    cache.set('coins_info', {
        'exp': (timezone.now() + timedelta(minutes=5)).timestamp(),
        'data': coins_info
    }, timeout=72 * 3600)

    cache.delete(fetch_key)


def get_coins_info_from_ohlc() -> List[dict]:
    yesterday_23 = (timezone.now() - timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)
    assets = Asset.live_objects.exclude(symbol__in=["IRT", "USDT"])
    data = []
    for asset in assets:
        pair = asset.symbol + 'IRT'

        price = fetch_external_price_by_symbol(pair, SELL)
        if asset.symbol == 'XAUM':
            price *= 1000
        yesterday = Ohlc1H.objects.filter(symbol=pair, timestamp=yesterday_23).first()
        change_24h = 0
        if yesterday and yesterday.close > 0:
            change_24h = ((float(price) - float(yesterday.close)) / float(yesterday.close)) * 100

        coin_data = {
            'coin': asset.symbol,
            'change_24h': change_24h,
            'price': price,
            'volume_24h': 0,
            'change_7d': 0,
            'high_24h': 0,
            'low_24h': 0,
            'change_1h': 0,
            'cmc_rank': 0,
            'market_cap': 0,
            'circulating_supply': 0,
            'weekly_trend_url': ''
        }

        data.append(coin_data)

    return data
