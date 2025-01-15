from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from decimal import Decimal
import requests
from django.db import transaction
from django.db.models import Q, Avg
from django.utils.timezone import make_aware
import pytz
from ohlc.models import Candle, MaterializedCandle
from ledger.models import Asset


class Command(BaseCommand):
    help = 'Backfills historical OHLC data from Wallgold API'

    def fetch_data(self, chart_type: str):
        response = requests.get(
            'https://api.wallgold.ir/api/chart',
            params={
                'symbol': 'GLD_18C_750TMN',
                'chartType': chart_type
            }
        )
        if response.ok and response.json().get('success'):
            return response.json()['result']['data']
        return None

    def cleanUp(self):
        try:
            # Delete all records from both tables
            candle_count = Candle.objects.all().delete()[0]
            materialized_count = MaterializedCandle.objects.all().delete()[0]

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted {candle_count} Candles and {materialized_count} MaterializedCandles'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error cleaning up candles: {str(e)}')
            )

    def handle(self, *args, **kwargs):
        self.cleanUp()
        gold_asset = Asset.objects.filter(
            Q(symbol__startswith='XAU') | Q(symbol__startswith='XAUM'),
            enable=True
        ).first()

        if not gold_asset:
            self.stdout.write(self.style.ERROR('No gold asset found'))
            return

        symbol = f"{gold_asset.symbol}IRT"

        try:
            with transaction.atomic():
                # 1. First get yearly data (daily candles)
                yearly_data = self.fetch_data('yearly')
                if yearly_data:
                    for candle in yearly_data:
                        timestamp = datetime.strptime(candle['date'], '%Y-%m-%dT%H:%M:%SZ')
                        aware_timestamp = make_aware(timestamp, timezone=pytz.UTC)
                        Candle.objects.update_or_create(
                            symbol=symbol,
                            timestamp=aware_timestamp,
                            defaults={
                                'open': Decimal(candle['open']),
                                'high': Decimal(candle['high']),
                                'low': Decimal(candle['low']),
                                'close': Decimal(candle['close']),
                                'volume': Decimal('1')
                            }
                        )
                # 2. Get hourly data from monthly, weekly, and daily
                for timeframe in ['monthly', 'weekly', 'daily']:
                    data = self.fetch_data(timeframe)
                    if data:
                        for candle in data:
                            timestamp = datetime.strptime(candle['date'], '%Y-%m-%dT%H:%M:%SZ')
                            aware_timestamp = make_aware(timestamp, timezone=pytz.UTC)

                            Candle.objects.update_or_create(
                                symbol=symbol,
                                timestamp=aware_timestamp,
                                defaults={
                                    'open': Decimal(candle['open']),
                                    'high': Decimal(candle['high']),
                                    'low': Decimal(candle['low']),
                                    'close': Decimal(candle['close']),
                                    'volume': Decimal('1')
                                }
                            )
                self.stdout.write(self.style.SUCCESS(f'Added  {Candle.objects.count()} candles from wallgold chart'))

                # 3. Run aggregation to create MaterializedCandles
                aggregate_historical_data()
                self.stdout.write(self.style.SUCCESS('Successfully aggregated all candles'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error processing data: {str(e)}')
            )


def aggregate_historical_data():
    """
    Aggregates candles based on the actual data range in the Candles table,
    not based on current time
    """
    from ohlc.models import Candle, MaterializedCandle
    from django.db.models import Min, Max
    from django.db import transaction

    try:
        # Get the time range from existing candles
        time_range = Candle.objects.aggregate(
            start_time=Min('timestamp'),
            end_time=Max('timestamp')
        )

        start_time = time_range['start_time']
        end_time = time_range['end_time']

        if not start_time or not end_time:
            print("No candles found to aggregate")
            return

        gold_asset = Asset.objects.filter(
            Q(symbol__startswith='XAU') | Q(symbol__startswith='XAUM'),
            enable=True
        ).first()

        symbol = f"{gold_asset.symbol}IRT"

        with transaction.atomic():
            current_time = start_time

            while current_time <= end_time:
                # For 1-hour candles (from base candles)
                hour_end = current_time + timedelta(hours=1)
                hour_candles = Candle.objects.filter(
                    symbol=symbol,
                    timestamp__gte=current_time,
                    timestamp__lt=hour_end
                ).order_by('timestamp')

                if hour_candles.exists():
                    first_candle = hour_candles.first()
                    last_candle = hour_candles.last()

                    # Get high and low from all candles
                    agg = hour_candles.aggregate(
                        high_price=Max('high'),
                        low_price=Min('low'),
                        volume_sum=Avg('volume')
                    )

                    MaterializedCandle.objects.update_or_create(
                        symbol=symbol,
                        timestamp=current_time,
                        timeframe='1h',
                        defaults={
                            'open': first_candle.open,
                            'high': agg['high_price'],
                            'low': agg['low_price'],
                            'close': last_candle.close,
                            'volume': agg['volume_sum']
                        }
                    )

                # For 4-hour candles
                if current_time.hour % 4 == 0:
                    four_hour_end = current_time + timedelta(hours=4)
                    four_hour_candles = Candle.objects.filter(
                        symbol=symbol,
                        timestamp__gte=current_time,
                        timestamp__lt=four_hour_end
                    ).order_by('timestamp')

                    if four_hour_candles.exists():
                        first_candle = four_hour_candles.first()
                        last_candle = four_hour_candles.last()

                        agg = four_hour_candles.aggregate(
                            high_price=Max('high'),
                            low_price=Min('low'),
                            volume_sum=Avg('volume')
                        )

                        MaterializedCandle.objects.update_or_create(
                            symbol=symbol,
                            timestamp=current_time,
                            timeframe='4h',
                            defaults={
                                'open': first_candle.open,
                                'high': agg['high_price'],
                                'low': agg['low_price'],
                                'close': last_candle.close,
                                'volume': agg['volume_sum']
                            }
                        )

                # For daily candles
                if current_time.hour == 0:
                    day_end = current_time + timedelta(days=1)
                    day_candles = Candle.objects.filter(
                        symbol=symbol,
                        timestamp__gte=current_time,
                        timestamp__lt=day_end
                    ).order_by('timestamp')

                    if day_candles.exists():
                        first_candle = day_candles.first()
                        last_candle = day_candles.last()

                        agg = day_candles.aggregate(
                            high_price=Max('high'),
                            low_price=Min('low'),
                            volume_sum=Avg('volume')
                        )

                        MaterializedCandle.objects.update_or_create(
                            symbol=symbol,
                            timestamp=current_time,
                            timeframe='1d',
                            defaults={
                                'open': first_candle.open,
                                'high': agg['high_price'],
                                'low': agg['low_price'],
                                'close': last_candle.close,
                                'volume': agg['volume_sum']
                            }
                        )

                current_time += timedelta(hours=1)

        print(
            f"Successfully aggregated candles from {start_time} to {end_time} total {MaterializedCandle.objects.count()} materialized candles")

    except Exception as e:
        print(f"Error in aggregate_historical_data: {str(e)}")
        raise
