from collections import namedtuple
from decimal import Decimal

from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import CheckConstraint, Q

from accounts.models import Account
from ledger.utils.fields import get_amount_field

DEFAULT_MAKER_FEE = Decimal(0)
DEFAULT_TAKER_FEE = Decimal('0.002')


class PairSymbol(models.Model):
    IdName = namedtuple("PairSymbol", "id name tick_size")

    name = models.CharField(max_length=32, blank=True, unique=True)
    asset = models.ForeignKey('ledger.Asset', on_delete=models.PROTECT, related_name='pair')
    base_asset = models.ForeignKey('ledger.Asset', on_delete=models.PROTECT, related_name='trading_pair')

    custom_maker_fee = get_amount_field(null=True)
    custom_taker_fee = get_amount_field(null=True)

    tick_size = models.PositiveSmallIntegerField(default=2, validators=[MaxValueValidator(8)])
    step_size = models.PositiveSmallIntegerField(default=4, validators=[MaxValueValidator(8)])
    min_trade_quantity = get_amount_field(default=Decimal('0.0001'))
    max_trade_quantity = get_amount_field(default=Decimal('10000'))

    enable = models.BooleanField(default=False)
    strategy_enable = models.BooleanField(default=False)
    margin_enable = models.BooleanField(default=False)

    last_trade_time = models.DateTimeField(null=True, blank=True)
    last_trade_price = get_amount_field(null=True)

    @classmethod
    def get_by(cls, name):
        return cls.objects.get(name=name)

    def __str__(self):
        return self.name

    def save(self, **kwargs):
        self.name = f'{self.asset}{self.base_asset}'
        if not self.name:
            raise Exception('Could not set name for pair symbol!')
        return super(PairSymbol, self).save(**kwargs)

    def get_margin_position(self, account: Account, order_side, is_open_position: bool = None):
        from ledger.models.position import MarginPosition
        return MarginPosition.get_by(self, account=account, order_side=order_side, is_open_position=is_open_position)

    class Meta:
        unique_together = ('asset', 'base_asset')
        constraints = [
            CheckConstraint(check=Q(min_trade_quantity__gte=0, max_trade_quantity__gte=0,), name='check_market_pairsymbol_amounts', ),
        ]

    def get_fee_rate(self, account: Account, is_maker: bool) -> Decimal:
        if account.is_system():
            return Decimal(0)

        if is_maker:
            fees = [account.custom_maker_fee, self.custom_maker_fee, DEFAULT_MAKER_FEE]
        else:
            fees = [account.custom_taker_fee, self.custom_taker_fee, DEFAULT_TAKER_FEE]

        if fees[0] is None and account.get_voucher_wallet():
            return Decimal(0)

        for f in fees:
            if f is not None:
                return f

        return Decimal(0)
