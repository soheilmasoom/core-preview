from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from decimal import Decimal
import requests
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import make_aware
import pytz
from ohlc.models import Candle, MaterializedCandle
from ledger.models import Asset
from ohlc.tasks.gold import aggregate_materialized_candles


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

                        # For daily candles, create 24 hourly candles with the same values
                        for hour in range(24):
                            hourly_timestamp = aware_timestamp + timedelta(hours=hour)
                            Candle.objects.update_or_create(
                                symbol=symbol,
                                timestamp=hourly_timestamp,
                                defaults={
                                    'open': Decimal(candle['open']),
                                    'high': Decimal(candle['high']),
                                    'low': Decimal(candle['low']),
                                    'close': Decimal(candle['close']),
                                    'volume': Decimal('1')
                                }
                            )
                            self.stdout.write(f"Created hourly candle for {hourly_timestamp} from yearly data")

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
                            self.stdout.write(f"Created hourly candle for {aware_timestamp} from {timeframe} data")

                # 3. Run aggregation to create MaterializedCandles
                aggregate_materialized_candles()
                self.stdout.write(self.style.SUCCESS('Successfully aggregated all candles'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error processing data: {str(e)}')
            )
