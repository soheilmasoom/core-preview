from django.conf import settings
from django.db import models

from ledger.utils.external_price import SELL
from ledger.utils.fields import get_amount_field, get_group_id_field
from market.models import BaseTrade


class TradeRevenue(models.Model):
    """
    price = coin_price * base_price
    coin_price = coin_real_price * (1 +- coin_spread)
    base_price = base_real_price * (1 +- base_spread)
    """

    OTC_MARKET, OTC_PROVIDER, TAKER, MAKER, USER, MANUAL = 'otc-m', 'otc-p', 'taker', 'maker', 'user', 'manual'

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    symbol = models.ForeignKey('market.PairSymbol', on_delete=models.PROTECT)
    account = models.ForeignKey('accounts.Account', on_delete=models.PROTECT)
    side = models.CharField(max_length=8, choices=BaseTrade.SIDE_CHOICES)
    amount = get_amount_field()
    price = get_amount_field()
    group_id = get_group_id_field()
    source = models.CharField(max_length=8, choices=(
        (OTC_MARKET, OTC_MARKET), (OTC_PROVIDER, OTC_PROVIDER), (MAKER, MAKER), (TAKER, TAKER), (USER, USER),
        (MANUAL, MANUAL)
    ))
    fee_revenue = get_amount_field()
    value = get_amount_field()
    value_irt = get_amount_field(default=0)
    value_is_fake = models.BooleanField(default=False)

    coin_price = get_amount_field()

    coin_filled_price = get_amount_field(null=True)
    filled_amount = get_amount_field(null=True)
    gap_revenue = get_amount_field(validators=(), null=True)
    hedge_key = models.CharField(max_length=16, db_index=True, blank=True)

    base_usdt_price = get_amount_field(decimal_places=20)
    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)
    position = models.ForeignKey(to='ledger.MarginPosition', on_delete=models.CASCADE, null=True, blank=True)

    @classmethod
    def new(cls, user_trade: BaseTrade, group_id, source: str, hedge_key: str = '', ignore_trade_value=False, position=None):
        trade_volume = user_trade.amount * user_trade.price
        trade_value = trade_volume * user_trade.base_usdt_price

        coin_price = user_trade.price * user_trade.base_usdt_price

        value_is_fake = ignore_trade_value or bool(user_trade.account_id in (
            settings.OTC_ACCOUNT_ID, settings.MARKET_MAKER_ACCOUNT_ID, settings.TRADER_ACCOUNT_ID
        ))

        revenue = TradeRevenue(
            created=user_trade.created,
            account=user_trade.account,
            symbol=user_trade.symbol,
            side=user_trade.side,
            amount=user_trade.amount,
            price=user_trade.price,
            group_id=group_id,
            value=trade_value,
            value_irt=trade_volume * user_trade.base_irt_price,
            value_is_fake=value_is_fake,
            fee_revenue=user_trade.fee_revenue,

            source=source,
            hedge_key=hedge_key,
            coin_price=coin_price,
            base_usdt_price=user_trade.base_usdt_price,
            login_activity=user_trade.login_activity,
            position=position
        )

        if not hedge_key:
            revenue.coin_filled_price = revenue.coin_price
            revenue.filled_amount = revenue.amount
            revenue.gap_revenue = 0

        return revenue

    def get_gap_revenue(self):
        gap = self.amount * (self.coin_price - self.coin_filled_price)

        if self.side == SELL:
            gap = -gap

        return gap
