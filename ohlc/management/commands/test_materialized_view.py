from django.core.management.base import BaseCommand
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from ohlc.models import Candle, Ohlc1H, Ohlc1D
from ohlc.tasks.gold import refresh_materialized_views


class Command(BaseCommand):
    help = "Populate fake candles, refresh materialized views, query them, and clean up."

    def handle(self, *args, **options):
        fake_symbol = "FAKE_TEST_SYMBOL"
        start_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        num_candles = 120
        self.stdout.write(f"Creating {num_candles} fake candles for symbol '{fake_symbol}'...")

        # Step 1: Create fake candles
        candles = [
            Candle(
                symbol=fake_symbol,
                timestamp=start_time + timedelta(minutes=i),
                open=Decimal("5000.00") + i,
                high=Decimal("5010.00") + i,
                low=Decimal("4990.00") + i,
                close=Decimal("5005.00") + i,
                volume=Decimal("1.0"),
            )
            for i in range(num_candles)
        ]
        Candle.objects.filter(symbol=fake_symbol).delete()
        Candle.objects.bulk_create(candles)
        self.stdout.write(f"Created {len(candles)} candles.")

        # Step 2: Refresh materialized views
        self.stdout.write("Refreshing materialized views...")
        refresh_materialized_views()
        self.stdout.write("Materialized views refreshed.")

        # Step 3: Query materialized views using Django ORM
        self.stdout.write("Querying materialized views using ORM...")

        # Query Ohlc1H
        hourly_candles = Ohlc1H.objects.filter(symbol=fake_symbol).order_by("timestamp")
        self.stdout.write("Results from Ohlc1H:")
        for candle in hourly_candles:
            self.stdout.write(
                f"Timestamp: {candle.timestamp}, Open: {candle.open}, High: {candle.high}, "
                f"Low: {candle.low}, Close: {candle.close}, Volume: {candle.volume}"
            )

        # Query Ohlc1D
        daily_candles = Ohlc1D.objects.filter(symbol=fake_symbol).order_by("timestamp")
        self.stdout.write("Results from Ohlc1D:")
        for candle in daily_candles:
            self.stdout.write(
                f"Timestamp: {candle.timestamp}, Open: {candle.open}, High: {candle.high}, "
                f"Low: {candle.low}, Close: {candle.close}, Volume: {candle.volume}"
            )

        # Step 4: Clean up test data
        self.stdout.write("Cleaning up test data...")
        Candle.objects.filter(symbol=fake_symbol).delete()
