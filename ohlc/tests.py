from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from ledger.models import Asset
from ohlc.models import Candle, MaterializedCandle
from ohlc.tasks.gold import fetch_and_store_gold_candles, aggregate_materialized_candles


class OHLCTasksTests(TestCase):
    def setUp(self):
        # Create test asset
        self.gold_asset = Asset.objects.create(
            symbol='XAU',
            name='Gold',
            enable=True
        )
        self.symbol = 'XAUIRT'

    @patch('ohlc.tasks.gold.get_prices')
    def test_fetch_and_store_gold_candles(self, mock_get_prices):
        mock_get_prices.return_value = {self.symbol: Decimal('1000.00')}

        fetch_and_store_gold_candles()

        candle = Candle.objects.first()
        self.assertIsNotNone(candle)
        self.assertEqual(candle.symbol, self.symbol)
        self.assertEqual(candle.open, Decimal('1000.00'))
        self.assertEqual(candle.close, Decimal('1000.00'))

    def test_aggregate_materialized_candles(self):
        now = timezone.now()
        prices = [Decimal('1000.00'), Decimal('1100.00'), Decimal('900.00'), Decimal('1050.00')]
        for i, price in enumerate(prices):
            Candle.objects.create(
                symbol=self.symbol,
                timestamp=now - timedelta(minutes=i),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal('1')
            )

        # Run aggregation
        aggregate_materialized_candles()

        # Check 15min materialized candle
        mat_candle = MaterializedCandle.objects.filter(timeframe='15min').first()
        self.assertIsNotNone(mat_candle)
        self.assertEqual(mat_candle.high, Decimal('1100.00'))
        self.assertEqual(mat_candle.low, Decimal('900.00'))


class ChartAPITests(APITestCase):
    def setUp(self):
        self.gold_asset = Asset.objects.create(
            symbol='XAU',
            name='Gold',
            enable=True
        )
        self.symbol = 'XAUIRT'

        now = timezone.now()

        for i in range(60):
            Candle.objects.create(
                symbol=self.symbol,
                timestamp=now - timedelta(minutes=i),
                open=Decimal('1000.00'),
                high=Decimal('1000.00'),
                low=Decimal('1000.00'),
                close=Decimal('1000.00') + i,
                volume=Decimal('1')
            )

        MaterializedCandle.objects.create(
            symbol=self.symbol,
            timestamp=now - timedelta(minutes=15),
            timeframe='15min',
            open=Decimal('1000.00'),
            high=Decimal('1100.00'),
            low=Decimal('900.00'),
            close=Decimal('1050.00'),
            volume=Decimal('1')
        )

    def test_line_chart_hourly(self):
        url = reverse('chart-line-chart')
        response = self.client.get(url, {'symbol': self.symbol, 'type': 'hourly'})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(len(data) > 0)
        self.assertIn('timestamp', data[0])
        self.assertIn('close', data[0])

        self.assertEqual(len(data[0].keys()), 2)

    def test_line_chart_daily(self):
        url = reverse('chart-line-chart')
        response = self.client.get(url, {'symbol': self.symbol, 'type': 'daily'})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(len(data) > 0)
        self.assertIn('timestamp', data[0])
        self.assertIn('close', data[0])

    def test_line_chart_invalid_timeframe(self):
        url = reverse('chart-line-chart')
        response = self.client.get(url, {'symbol': self.symbol, 'type': 'invalid'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_line_chart_missing_symbol(self):
        url = reverse('chart-line-chart')
        response = self.client.get(url, {'type': 'daily'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())