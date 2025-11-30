import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import List

from django.db import models
from django.db.models import Sum
from simple_history.models import HistoricalRecords

from ledger.utils.fields import get_amount_field


@dataclasses.dataclass
class VaultData:
    coin: str
    balance: Decimal
    free: Decimal
    value_usdt: Decimal
    value_irt: Decimal


class Vault(models.Model):
    TYPES = PROVIDER, GATEWAY, HOT_WALLET, COLD_WALLET, BANK, APP, MANUAL = \
        'provider', 'gateway', 'hw', 'cw', 'bank', 'app', 'manual'
    MARKETS = SPOT, FUTURES = 'spot', 'futures'

    history = HistoricalRecords()

    updated = models.DateTimeField(db_index=True)

    name = models.CharField(max_length=32)

    type = models.CharField(max_length=8, choices=[(t, t) for t in TYPES])
    market = models.CharField(max_length=8, choices=[(t, t) for t in MARKETS], default=SPOT)
    key = models.CharField(max_length=128, blank=True)

    real_value = get_amount_field(default=Decimal())

    expected_max_value = models.PositiveIntegerField(null=True, blank=True)
    should_be_updated = models.BooleanField(default=True)

    extra = models.JSONField(null=True, blank=True)

    def __str__(self):
        return '%s %s %s' % (self.type, self.name, self.market)

    class Meta:
        unique_together = ('key', 'type', 'market')

    def update_vault_all_items(self, now, data: List[VaultData], real_vault_value: Decimal = None):
        coins = []

        for vd in data:
            VaultItem.objects.update_or_create(
                vault=self,
                coin=vd.coin,
                defaults={
                    'updated': now,
                    'balance': vd.balance,
                    'free': vd.free,
                    'value_usdt': vd.value_usdt,
                    'value_irt': vd.value_irt
                }
            )

            coins.append(vd.coin)

        VaultItem.objects.filter(
            vault=self
        ).exclude(
            coin__in=coins
        ).exclude(
            balance=0,
            value_usdt=0,
            value_irt=0
        ).update(
            balance=0,
            value_usdt=0,
            value_irt=0,
            updated=now,
        )

        self.update_real_value(now, real_vault_value)

    def update_real_value(self, now: datetime, real_vault_value: Decimal = None):
        self.updated = now

        if real_vault_value is not None:
            self.real_value = real_vault_value
        else:
            self.real_value = VaultItem.objects.filter(vault=self).aggregate(value=Sum('value_usdt'))['value'] or 0

        self.save(update_fields=['updated', 'real_value'])


class VaultItem(models.Model):
    history = HistoricalRecords()

    updated = models.DateTimeField(db_index=True)

    vault = models.ForeignKey(Vault, on_delete=models.CASCADE)
    coin = models.CharField(max_length=32, db_index=True)
    balance = get_amount_field(validators=())
    free = get_amount_field(validators=())
    value_usdt = get_amount_field(validators=(), default=0)
    value_irt = get_amount_field(validators=(), default=0)

    expected_min_balance = get_amount_field(null=True)

    class Meta:
        unique_together = ('vault', 'coin')

    def __str__(self):
        return '%s %s' % (self.vault, self.coin)


class ReservedAsset(models.Model):
    history = HistoricalRecords()

    updated = models.DateTimeField()

    coin = models.CharField(max_length=32, unique=True)
    amount = get_amount_field(validators=())

    value_usdt = get_amount_field(validators=())
    value_irt = get_amount_field(validators=())

    def __str__(self):
        return self.coin


class AssetPrice(models.Model):
    history = HistoricalRecords()

    updated = models.DateTimeField()

    coin = models.CharField(max_length=32, unique=True)
    price = get_amount_field(decimal_places=12)

    def __str__(self):
        return self.coin
