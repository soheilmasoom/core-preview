import math
from datetime import datetime
from decimal import Decimal
from typing import Union

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import CheckConstraint, Q
from simple_history.models import HistoricalRecords

from ledger.fields import WithdrawSources
from ledger.models import Asset
from ledger.utils.blocklink import get_blocklink_requester
from ledger.utils.dto import NetworkInfo
from ledger.utils.fields import get_amount_field
from ledger.utils.price import get_last_price

MIN_PRECISION_AMOUNT = Decimal('0.00000001')


class NetworkAsset(models.Model):
    history = HistoricalRecords()

    asset = models.ForeignKey('ledger.Asset', on_delete=models.PROTECT)
    network = models.ForeignKey('ledger.Network', on_delete=models.PROTECT)

    withdraw_fee = get_amount_field()
    withdraw_min = get_amount_field()
    withdraw_max = get_amount_field()
    withdraw_precision = models.PositiveSmallIntegerField()

    hedger_withdraw_enable = models.BooleanField(default=False)
    hedger_deposit_enable = models.BooleanField(default=False)

    can_deposit = models.BooleanField(default=False)
    can_withdraw = models.BooleanField(default=False)

    allow_provider_withdraw = models.BooleanField(default=True)
    update_fee_with_provider = models.BooleanField(default=True)
    update_with_provider = models.BooleanField(default=True)
    last_provider_update = models.DateTimeField(null=True, blank=True)

    deposit_min = get_amount_field(
        default=MIN_PRECISION_AMOUNT,
        validators=(MinValueValidator(MIN_PRECISION_AMOUNT),),
    )

    expected_hw_balance = get_amount_field(default=0)

    max_allowed_daily_deposit_value = models.PositiveIntegerField(null=True, blank=True)

    network_order = models.PositiveSmallIntegerField(default=0)

    withdraw_source = WithdrawSources.get_db_field()

    contract = models.CharField(max_length=128, blank=True)

    def can_deposit_enabled(self, check_provider: bool = True) -> bool:
        system_enable = self.network.can_deposit and self.can_deposit

        return system_enable and (not check_provider or self.hedger_deposit_enable)

    def can_withdraw_enabled(self, check_provider: bool = True) -> bool:
        system_enable = self.network.can_withdraw and self.can_withdraw

        return system_enable and (not check_provider or self.hedger_withdraw_enable)

    def get_min_deposit(self) -> Union[Decimal, None]:
        return self.deposit_min

    def get_withdraw_precision(self):
        return self.withdraw_precision

    @classmethod
    def get_active_q(cls, active: bool = True) -> Q:
        q = Q(asset__enable=True) & \
            (Q(can_deposit=True, network__can_deposit=True) | Q(can_withdraw=True, network__can_withdraw=True))

        if not active:
            q = ~q

        return q

    def __str__(self):
        return '%s - %s' % (self.network, self.asset)

    class Meta:
        unique_together = ('asset', 'network')
        constraints = [
            CheckConstraint(
                check=Q(withdraw_fee__gte=0, withdraw_min__gte=0, withdraw_max__gte=0),
                name='check_ledger_network_amounts'
            ),
        ]

    def update_network_asset_with_provider(self, info: NetworkInfo, now: datetime):
        self.hedger_withdraw_enable = info.withdraw_enable
        self.hedger_deposit_enable = info.deposit_enable
        self.last_provider_update = now

        to_update_fields = ['hedger_withdraw_enable', 'hedger_deposit_enable', 'last_provider_update']

        if self.update_fee_with_provider:
            withdraw_fee = info.withdraw_fee
            withdraw_min = info.withdraw_min

            withdraw_fee *= Decimal('1.5')
            withdraw_min = max(withdraw_min, 2 * withdraw_fee)

            price = get_last_price(self.asset.symbol + Asset.USDT)

            if price and withdraw_min:
                multiplier = max(math.ceil(5 / (price * withdraw_min)), 1)  # withdraw_min >= 5$
                withdraw_min *= multiplier

            if price and withdraw_fee:
                multiplier = max(math.ceil(Decimal('0.2') / (price * withdraw_fee)), 1)  # withdraw_fee >= 0.2$
                withdraw_fee *= multiplier

            withdraw_min = max(
                withdraw_min,
                info.withdraw_min + withdraw_fee - info.withdraw_fee
            )

            self.withdraw_fee = withdraw_fee
            self.withdraw_min = withdraw_min
            self.withdraw_max = info.withdraw_max

            to_update_fields.extend(['withdraw_fee', 'withdraw_min', 'withdraw_max'])

        self.save(update_fields=to_update_fields)

    def update_info_with_blocklink(self):
        resp = get_blocklink_requester().get_contract_info(coin=self.asset.symbol, network=self.network.symbol)

        if resp.ok:
            data = resp.data
            self.withdraw_precision = data['precision']
            self.contract = data['contract']
            self.save(update_fields=['withdraw_precision', 'contract'])
            return True
        else:
            return False
