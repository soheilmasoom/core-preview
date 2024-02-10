from enum import Enum

from django.db import models
from simple_history.models import HistoricalRecords

from ledger.utils.fields import get_amount_field

from decimal import Decimal


class SystemConfig(models.Model):
    history = HistoricalRecords()

    TRANSFER_STATUS = ALLOW, BAN, BAN_CRYPTO, BAN_FIAT = 'allow', 'ban', 'ban_crypto', 'ban_fiat'

    name = models.CharField(max_length=32)
    active = models.BooleanField()
    is_consultation_available = models.BooleanField(default=False)

    withdraw_fee_min = models.SmallIntegerField(default=1000)
    withdraw_fee_max = models.SmallIntegerField(default=5000)
    withdraw_fee_percent = get_amount_field(default=Decimal('5'))

    hedge_irt_by_internal_market = models.BooleanField(default=False)
    hedge_coin_otc_from_internal_market = models.BooleanField(default=True)

    max_margin_leverage = models.SmallIntegerField(default=5)
    default_margin_leverage = models.SmallIntegerField(default=3)

    total_margin_usdt_base = get_amount_field(default=Decimal('10_000'))
    total_margin_irt_base = get_amount_field(default=Decimal('500_000_000'))
    total_user_margin_usdt_base = get_amount_field(default=Decimal('10_000'))
    total_user_margin_irt_base = get_amount_field(default=Decimal('500_000_000'))
    liquidation_level = get_amount_field(default=Decimal('1.1'))
    insurance_fee = get_amount_field(default=Decimal('0.02'))

    open_pay_id_to_all = models.BooleanField(default=False)

    limit_ipg_to_users_without_payment = models.BooleanField(default=False)

    withdraw_status = models.CharField(max_length=16, choices=[(s, s) for s in TRANSFER_STATUS], default=ALLOW)
    deposit_status = models.CharField(max_length=16, choices=[(s, s) for s in TRANSFER_STATUS], default=ALLOW)

    default_max_allowed_coin_network_daily_deposit_value = models.PositiveSmallIntegerField(default=300)

    def __str__(self):
        return self.name

    @classmethod
    def get_system_config(cls) -> 'SystemConfig':
        return SystemConfig.objects.filter(
            active=True
        ).first() or SystemConfig()
