from django.contrib.postgres.indexes import BrinIndex
from django.db import models


class Candle(models.Model):
    """Base model for 1-minute OHLC candles"""
    symbol = models.CharField(max_length=20, db_index=True)
    timestamp = models.DateTimeField()
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=8)

    class Meta:
        unique_together = ('symbol', 'timestamp')
        indexes = [
            models.Index(fields=['symbol']),
            BrinIndex(fields=['timestamp'], pages_per_range=128),
        ]


class Ohlc1H(models.Model):
    row_id = models.BigIntegerField(primary_key=True)
    symbol = models.CharField(max_length=20)
    timestamp = models.DateTimeField()
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=8)

    class Meta:
        managed = False  # Prevent Django from trying to manage this table
        db_table = 'ohlc_1h'
        unique_together = ('symbol', 'timestamp')


class Ohlc1D(models.Model):
    row_id = models.BigIntegerField(primary_key=True)
    symbol = models.CharField(max_length=20)
    timestamp = models.DateTimeField()
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=8)

    class Meta:
        managed = False
        db_table = 'ohlc_1d'
        unique_together = ('symbol', 'timestamp')


class MaterializedCandle(models.Model):
    """Pre-calculated candles for common timeframes"""
    TIMEFRAME_CHOICES = [
        ('15min', '15 Minutes'),
        ('1h', '1 Hour'),
        ('4h', '4 Hours'),
        ('1d', '1 Day'),
    ]

    symbol = models.CharField(max_length=20)
    timestamp = models.DateTimeField()
    timeframe = models.CharField(max_length=10, choices=TIMEFRAME_CHOICES)
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=8)

    class Meta:
        unique_together = ('symbol', 'timestamp', 'timeframe')
        indexes = [
            models.Index(fields=['symbol', 'timeframe']),
            BrinIndex(fields=['symbol', 'timeframe', 'timestamp'], pages_per_range=128),
        ]
