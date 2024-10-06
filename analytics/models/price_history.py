from django.db import models

from ledger.utils.fields import get_amount_field


class Symbol(models.Model):
    SOURCES = TGJU, NOBITEX, MEXC, EXNESS, BINANCE = 'tgju', 'nobitex', 'mexc', 'exness', 'binance'

    name = models.CharField(max_length=64)
    source = models.CharField(max_length=64, choices=[(s, s) for s in SOURCES])
    market_id = models.CharField(max_length=64, blank=True)
    account_id = models.CharField(max_length=64, blank=True)
    auth = models.CharField(max_length=2048, blank=True)

    auto_collect = models.BooleanField(default=True)

    class Meta:
        unique_together = ('name', 'source')

    def __str__(self):
        return f'{self.source} / {self.name}'


class SymbolPrice(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)
    created = models.DateTimeField()
    frame = models.PositiveSmallIntegerField(default=5)

    open = get_amount_field()
    close = get_amount_field()
    high = get_amount_field()
    low = get_amount_field()
    amount = get_amount_field(default=0)
    volume = get_amount_field(default=0)

    class Meta:
        unique_together = ('symbol', 'created', 'frame')
