import logging

from django.db import models

from ledger.models import Wallet
from ledger.utils.external_price import BUY, SELL
from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class BaseTrade(models.Model):
    SIDE_CHOICES = [(BUY, BUY), (SELL, SELL)]

    side = models.CharField(max_length=8, choices=SIDE_CHOICES)
    amount = get_amount_field()
    price = get_amount_field()
    is_maker = models.BooleanField()

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    symbol = models.ForeignKey('market.PairSymbol', on_delete=models.PROTECT)
    account = models.ForeignKey('accounts.Account', on_delete=models.PROTECT)

    market = models.CharField(
        max_length=8,
        choices=Wallet.MARKET_CHOICES,
    )
    base_irt_price = get_amount_field()
    base_usdt_price = get_amount_field()

    fee_amount = get_amount_field()  # trader fee amount
    fee_usdt_value = get_amount_field()  # trader fee value

    fee_revenue = get_amount_field()

    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def irt_value(self):
        return self.amount * self.price * self.base_irt_price

    @property
    def usdt_value(self):
        return self.amount * self.price * self.base_usdt_price

    def get_paying_amount(self):
        if self.side == BUY:
            return self.amount * self.price
        else:
            return self.amount

    def get_receiving_amount(self):
        if self.side == SELL:
            return self.amount * self.price
        else:
            return self.amount

    def get_net_receiving_amount(self):
        return self.get_receiving_amount() - self.fee_amount

    def get_net_receiving_value(self):
        return self.usdt_value - self.fee_usdt_value

    class Meta:
        abstract = True
