from datetime import datetime, timezone

from django.test import TestCase
from unittest.mock import patch
from decimal import Decimal

from ohlc.services import create_one_minute_candles
from ohlc.models import Candle
from ledger.models import Asset


class CandlesTests(TestCase):
    def setUp(self):
        self.gold_asset = Asset.objects.create(
            symbol='XAU',
            name='Gold',
            enable=True
        )
        self.symbol = 'XAUIRT'
        self.aligned_time = datetime(2025, 1, 1, 5, 0, tzinfo=timezone.utc)

    @patch('ohlc.services.get_prices')
    def test_adding_candle(self, mock_get_prices):
        mock_get_prices.return_value = {self.symbol: Decimal('5000.00')}
        timestamp = self.aligned_time.replace(second=35)
        create_one_minute_candles([self.symbol], timestamp)
        self.assertEqual(Candle.objects.count(), 1)
        candle = Candle.objects.first()
        self.assertIsNotNone(candle)
        self.assertEqual(candle.symbol, self.symbol)
        self.assertEqual(candle.open, Decimal('5000.00'))
        self.assertEqual(candle.close, Decimal('5000.00'))
        self.assertEqual(candle.timestamp, self.aligned_time)
        self.assertEqual(candle.volume, Decimal('1'))

    @patch('ohlc.services.get_prices')
    def test_duplicate_candle_same_minute(self, mock_get_prices):
        Candle.objects.create(
            symbol=self.symbol,
            timestamp=self.aligned_time,
            open=Decimal('5000.00'),
            high=Decimal('5000.00'),
            low=Decimal('5000.00'),
            close=Decimal('5000.00'),
            volume=Decimal('1')
        )

        # Try to create another candle for same minute with different price
        mock_get_prices.return_value = {self.symbol: Decimal('5500.00')}
        timestamp = self.aligned_time.replace(second=35)

        create_one_minute_candles([self.symbol], timestamp)

        # Verify only one candle exists and it has the original values
        self.assertEqual(Candle.objects.count(), 1)
        candle = Candle.objects.first()
        self.assertEqual(candle.timestamp, self.aligned_time)
        self.assertEqual(candle.open, Decimal('5000.00'))
        self.assertEqual(candle.close, Decimal('5000.00'))
        self.assertEqual(candle.volume, Decimal('1'))
