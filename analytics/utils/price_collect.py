from datetime import datetime, timedelta

import requests
from django.db.models import Max, Min
from django.utils import timezone

from analytics.models import Symbol, SymbolPrice


def _collect_mexc_prices(symbol: Symbol, start: datetime, end: datetime):
    url = f'https://www.mexc.com/api/platform/spot/kline/web/kline/query?interval=Min5&openPriceMode=LAST_CLOSE&' \
          f'start={int(start.timestamp())}&end={int(end.timestamp())}&symbolId={symbol.market_id}'

    resp = requests.get(url).json()

    for d in resp['data']:
        SymbolPrice.objects.update_or_create(
            symbol=symbol,
            created=datetime.fromtimestamp(d['t']).astimezone(),
            defaults={
                'open': d['o'],
                'close': d['c'],
                'high': d['h'],
                'low': d['l'],
                'amount': d['a'],
                'volume': d['v'],
            }
        )


def collect_mexc_prices(symbol: Symbol):
    assert symbol.source == Symbol.MEXC

    end = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=1)
    start = end - timedelta(days=180)

    last_date = SymbolPrice.objects.filter(symbol=symbol).aggregate(last=Max('created'))['last']

    if last_date:
        start = max(start, last_date)

    step = timedelta(days=5)

    while start < end:
        print(f"Collecting {symbol} @ {start}")
        _collect_mexc_prices(symbol, start, start + step)
        start += step


def collect_tgju_prices(symbol: Symbol):
    assert symbol.source == Symbol.TGJU

    end = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=1)
    start = end - timedelta(days=180)

    last_date = SymbolPrice.objects.filter(symbol=symbol).aggregate(last=Max('created'))['last']

    if last_date:
        start = max(start, last_date)

    url = f'https://dashboard-api.tgju.org/v1/tv2/history?' \
          f'symbol={symbol.market_id}&resolution=5&from={int(start.timestamp())}&to={int(end.timestamp())}'

    resp = requests.get(url).json()

    for i in range(len(resp['t'])):
        SymbolPrice.objects.update_or_create(
            symbol=symbol,
            created=datetime.fromtimestamp(resp['t'][i]).astimezone(),
            defaults={
                'open': resp['o'][i] / 10,
                'close': resp['c'][i] / 10,
                'high': resp['h'][i] / 10,
                'low': resp['l'][i] / 10,
            }
        )


def _collect_nobitex_prices(symbol: Symbol, start: datetime, end: datetime):
    url = f'https://api.nobitex.ir/market/udf/history?' \
          f'symbol={symbol.market_id}&resolution=5&from={int(start.timestamp())}&to={int(end.timestamp())}&countback=1000'

    resp = requests.get(url).json()

    for i in range(len(resp['t'])):
        SymbolPrice.objects.update_or_create(
            symbol=symbol,
            created=datetime.fromtimestamp(resp['t'][i]).astimezone(),
            defaults={
                'open': resp['o'][i],
                'close': resp['c'][i],
                'high': resp['h'][i],
                'low': resp['l'][i],
                'volume': resp['v'][i],
            }
        )


def collect_nobitex_prices(symbol: Symbol):
    assert symbol.source == Symbol.NOBITEX

    end = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=1)
    start = end - timedelta(days=180)

    last_date = SymbolPrice.objects.filter(symbol=symbol).aggregate(last=Max('created'))['last']

    if last_date:
        start = max(start, last_date)

    step = timedelta(days=1)

    while start < end:
        print(f"Collecting {symbol} @ {start}")
        _collect_nobitex_prices(symbol, start, start + step)
        start += step


EXNESS_TIMEFRAME = 60


def _collect_exness_prices(symbol: Symbol, end: datetime):
    url = f'https://api.exweb.mobi/rtapi/mt5/trial1/v1/accounts/{symbol.account_id}/instruments/{symbol.market_id}/' \
          f'candles?time_frame={EXNESS_TIMEFRAME}&from={int(end.timestamp() * 1000)}&count=-1000'

    resp = requests.get(url, headers={
        'Authorization': f'Bearer {symbol.auth}'
    }).json()

    for d in resp['price_history']:
        SymbolPrice.objects.update_or_create(
            symbol=symbol,
            created=datetime.fromtimestamp(d['t'] / 1000).astimezone(),
            defaults={
                'open': d['o'],
                'close': d['c'],
                'high': d['h'],
                'low': d['l'],
                'volume': d['v'],
            }
        )


def collect_exness_prices(symbol: Symbol, days: int = 180):
    assert symbol.source == Symbol.EXNESS

    current_prices = SymbolPrice.objects.filter(symbol=symbol).aggregate(first=Min('created'), last=Max('created'))
    first_date = current_prices['first']
    last_date = current_prices['last']

    if first_date:
        end = first_date
        start = last_date - timedelta(days=days)
    else:
        end = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=1)
        start = end - timedelta(days=days)

    while start < end:
        print(f"Collecting {symbol} @ {start}")
        _collect_exness_prices(symbol, end)

        current_prices = SymbolPrice.objects.filter(symbol=symbol).aggregate(first=Min('created'))
        end = current_prices['first'] - timedelta(minutes=EXNESS_TIMEFRAME)
