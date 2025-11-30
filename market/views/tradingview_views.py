import logging
from datetime import timedelta, datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.utils.precision import floor_precision
from market.models import PairSymbol, Trade
from market.utils.datetime_utils import ceil_date, floor_date

logger = logging.getLogger(__name__)


class OHLCVSerializer:
    def __init__(self, candles, symbol):
        self.candles = candles
        self.symbol = symbol

    def format_data(self):
        return [self.format_single_obj(obj) for obj in self.candles]

    @staticmethod
    def get_timestamp(obj):
        return int(obj['timestamp'].timestamp() * 1000)

    def get_open(self, obj):
        return self.format_price(self.symbol, obj['open'])

    def get_high(self, obj):
        return self.format_price(self.symbol, obj['high'])

    def get_low(self, obj):
        return self.format_price(self.symbol, obj['low'])

    def get_close(self, obj):
        return self.format_price(self.symbol, obj['close'])

    def get_volume(self, obj):
        if obj['volume'] is None:
            return
        return floor_precision(obj['volume'], self.symbol.step_size)

    @staticmethod
    def format_price(symbol: PairSymbol, price: Decimal):
        if price is None:
            return
        return floor_precision(price, symbol.tick_size)

    def format_single_obj(self, obj):
        return {
            'time': self.get_timestamp(obj),
            'open': self.get_open(obj),
            'high': self.get_high(obj),
            'low': self.get_low(obj),
            'close': self.get_close(obj),
            'volume': self.get_volume(obj),
        }


class OHLCVAPIView(APIView):
    authentication_classes = ()
    permission_classes = ()

    @classmethod
    def append_empty_candles(cls, candles, interval, start, end):
        if not candles:
            return candles

        start = ceil_date(start, seconds=interval.total_seconds())
        end = floor_date(end, seconds=interval.total_seconds())
        if interval.total_seconds() > 3600:
            end -= interval

        first_candle = candles[0]
        candle_datetime = first_candle['timestamp']
        current_candle = first_candle
        start_padding_count = int((first_candle['timestamp'] - start).total_seconds() // interval.total_seconds())
        first_open = first_candle['open']
        start_padding = [{
            'timestamp': start + interval * i,
            'open': first_open, 'high': first_open, 'low': first_open, 'close': first_open, 'volume': Decimal(0)
        } for i in range(start_padding_count)]
        candles = start_padding + candles
        included_timestamps = {candle['timestamp']: candle for candle in candles}

        position = start_padding_count
        while candle_datetime < end:
            close = current_candle['close']
            candle_datetime += interval
            position += 1
            if candle_datetime in included_timestamps:
                current_candle = included_timestamps[candle_datetime]
                continue
            candles.insert(
                position, {
                    'timestamp': candle_datetime, 'open': close, 'high': close, 'low': close, 'close': close,
                    'volume': Decimal(0)
                }
            )
        return candles

    def get(self, request):
        symbol = request.query_params.get('symbol')
        if not symbol:
            raise ValidationError(f'symbol is required')

        symbol = get_object_or_404(PairSymbol, name=symbol.upper(), enable=True)

        start = request.query_params.get('from', (timezone.now() - timedelta(hours=24)).timestamp())
        end = request.query_params.get('to', timezone.now().timestamp())
        interval = request.query_params.get('resolution')
        if str(interval).isdigit():
            interval = int(interval) * 60
        elif str(interval) in ('1h', '1H'):
            interval = 3600
        elif str(interval) in ('1d', '1D'):
            interval = 24 * 3600
        elif str(interval) in ('7d', '7D'):
            interval = 7 * 24 * 3600
        else:
            interval = 60

        count_back = request.query_params.get('countBack', 0)
        start_datetime = datetime.fromtimestamp(int(start)).astimezone()
        end_datetime = datetime.fromtimestamp(int(end)).astimezone()
        candles = Trade.get_grouped_by_interval(
            symbol_id=symbol.id,
            interval_in_secs=int(interval),
            start=start_datetime,
            end=end_datetime,
        )
        candles = OHLCVAPIView.append_empty_candles(
            candles, timedelta(seconds=int(interval)), start_datetime, end_datetime
        )
        if candles and count_back:
            candles = candles[-int(count_back):]
        results = OHLCVSerializer(candles=candles, symbol=symbol).format_data()
        return Response(results, status=status.HTTP_200_OK)
