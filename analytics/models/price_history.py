from django.db import models

from ledger.utils.fields import get_amount_field


class Symbol(models.Model):
    SOURCES = TGJU, NOBITEX, MEXC = 'tgju', 'nobitex', 'mexc'

    name = models.CharField(max_length=64)
    source = models.CharField(max_length=64, choices=[(s, s) for s in SOURCES])
    exchange_id = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = ('name', 'source')

    def __str__(self):
        return f'{self.source} / {self.name}'


class SymbolPrice(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)
    created = models.DateTimeField()

    open = get_amount_field()
    close = get_amount_field()
    high = get_amount_field()
    low = get_amount_field()
    amount = get_amount_field(default=0)
    volume = get_amount_field(default=0)

    class Meta:
        unique_together = ('symbol', 'created')
