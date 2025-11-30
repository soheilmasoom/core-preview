from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from redis.client import Redis

from accounts.utils.validation import DAY
from ledger.utils.cache import cache_for
from market.models import PairSymbol

PREFIX_LAST_TRADE = 'market:top'
market_redis = Redis.from_url(settings.MARKET_CACHE_LOCATION, decode_responses=True)


def set_last_trade_price(symbol: PairSymbol):
    hour = timezone.now().hour
    key = '%s:%s' % (PREFIX_LAST_TRADE, hour)
    market_redis.hset(key, str(symbol.id), str(symbol.last_trade_price))
    market_redis.expire(key, 2 * DAY)


def get_yesterday_prices() -> dict:
    hour = timezone.now().hour + 1
    key = '%s:%s' % (PREFIX_LAST_TRADE, hour)
    prices = market_redis.hgetall(key)
    return {int(s): Decimal(p) for (s, p) in prices.items()}


@cache_for()
def get_symbol_prices():
    last_prices = dict(PairSymbol.objects.filter(enable=True).values_list('id', 'last_trade_price'))

    return {
        'last': last_prices,
        'yesterday': get_yesterday_prices()
    }
