from django.core.management.base import BaseCommand
from datetime import datetime
from decimal import Decimal
import requests
from django.db import transaction
from ohlc.models import MaterializedCandle
from ledger.models import Asset
from django.db.models import Q


class Command(BaseCommand):
    help = 'Backfills historical OHLC data from Wallgold API'

    def handle(self, *args, **kwargs):
        gold_asset = Asset.objects.filter(
            Q(symbol__startswith='XAU') | Q(symbol__startswith='XAUM'),
            enable=True
        ).first()

        if not gold_asset:
            self.stdout.write(self.style.ERROR('No gold asset found'))
            return

        symbol = f"{gold_asset.symbol}IRT"

        timeframes = {
            'daily': {'api_type': 'daily', 'model': MaterializedCandle, 'frame': '1h'},
            'weekly': {'api_type': 'weekly', 'model': MaterializedCandle, 'frame': '4h'},
            'monthly': {'api_type': 'monthly', 'model': MaterializedCandle, 'frame': '1d'},
        }

        for timeframe, config in timeframes.items():
            self.stdout.write(f"Fetching {timeframe} data...")

            try:
                response = requests.get(
                    f'https://api.wallgold.ir/api/chart',
                    params={
                        'symbol': 'GLD_18C_750TMN',
                        'chartType': config['api_type']
                    }
                )

                if not response.ok:
                    self.stdout.write(self.style.ERROR(f'Failed to fetch {timeframe} data'))
                    continue

                data = response.json()
                if not data.get('success'):
                    self.stdout.write(self.style.ERROR(f'API error for {timeframe}'))
                    continue

                with transaction.atomic():
                    for candle_data in data['result']['data']:
                        timestamp = datetime.strptime(
                            candle_data['date'],
                            '%Y-%m-%dT%H:%M:%SZ'
                        )

                        if config['model'].objects.filter(
                                symbol=symbol,
                                timestamp=timestamp,
                                timeframe=config['frame']
                        ).exists():
                            self.stdout.write(f"Skipping existing candle for {timestamp}")
                            continue

                        config['model'].objects.create(
                            symbol=symbol,
                            timestamp=timestamp,
                            timeframe=config['frame'],
                            open=Decimal(candle_data['open']),
                            high=Decimal(candle_data['high']),
                            low=Decimal(candle_data['low']),
                            close=Decimal(candle_data['close']),
                            volume=Decimal('1')
                        )
                        self.stdout.write(f"Created candle for {timestamp}")

                self.stdout.write(
                    self.style.SUCCESS(f'Successfully processed {timeframe} data')
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error processing {timeframe} data: {str(e)}')
                )
