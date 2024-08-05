from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.db.models import CheckConstraint, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import Account
from ledger.exceptions import SmallAmountTrade, LargeAmountTrade, NoPriceError
from ledger.models import Asset, Wallet
from ledger.utils.external_price import get_other_side, BUY, SELL
from ledger.utils.fields import get_amount_field
from ledger.utils.otc import get_trading_pair
from ledger.utils.precision import floor_precision, get_presentation_amount
from ledger.utils.price import get_depth_price, get_price, USDT_IRT
from ledger.utils.random import secure_uuid4
from market.consts import OTC_MIN_HARD_FIAT_VALUE, OTC_MAX_HARD_FIAT_VALUE
from market.models import BaseTrade
from market.utils.trade import get_fee_info


class OTCRequest(BaseTrade):
    # EXPIRE_TIME = 6
    EXPIRATION_TIME = 11

    ORDER_TYPES = LIMIT, MARKET = 'limit', 'market'
    TYPE_CHOICES = [(t, t) for t in ORDER_TYPES]

    EXPIRATIONS = H1, D1, D3, D7 = 'h1', 'd1', 'd3', 'd7'
    EXPIRATION_CHOICES = [(e, e) for e in EXPIRATIONS]

    created = models.DateTimeField(auto_now_add=True)
    token = models.UUIDField(default=secure_uuid4, db_index=True)

    from_asset = models.ForeignKey(to=Asset, on_delete=models.CASCADE, related_name='from_otc_requests')
    to_asset = models.ForeignKey(to=Asset, on_delete=models.CASCADE, related_name='to_otc_requests')
    from_amount = get_amount_field(null=True)
    to_amount = get_amount_field(null=True)

    gtd = models.DateTimeField(null=True, db_index=True, blank=True)
    trigger_price = get_amount_field(null=True)
    type = models.CharField(max_length=16, default=MARKET, choices=TYPE_CHOICES)

    @property
    def is_maker(self) -> bool:
        return False

    @classmethod
    def get_gtd_from_delta(cls, delta):
        delta_mapping = {
            cls.H1: timedelta(hours=1),
            cls.D1: timedelta(days=1),
            cls.D3: timedelta(days=3),
            cls.D7: timedelta(days=7)
        }
        if delta not in delta_mapping:
            raise ValueError("Invalid delta value")
        return datetime.now() + delta_mapping[delta]

    @classmethod
    def new_trade(cls, account: Account, market: str, from_asset: Asset, to_asset: Asset, order_type: str,
                  from_amount: Decimal = None, to_amount: Decimal = None, allow_dust: bool = False,
                  check_enough_balance: bool = True, gtd: datetime = None, trigger_price: Decimal = None) -> 'OTCRequest':

        assert order_type in cls.ORDER_TYPES
        assert from_amount or to_amount
        assert (from_amount or to_amount) > 0

        otc_request = cls.get_otc_request(
            account=account,
            from_asset=from_asset,
            to_asset=to_asset,
            from_amount=from_amount,
            to_amount=to_amount,
            market=market,
            order_type=order_type,
            gtd=gtd,
            trigger_price=trigger_price
        )

        if not allow_dust:
            otc_irt_value = otc_request.irt_value

            if otc_irt_value < OTC_MIN_HARD_FIAT_VALUE:
                raise SmallAmountTrade()

            if otc_irt_value > OTC_MAX_HARD_FIAT_VALUE:
                raise LargeAmountTrade()

        if check_enough_balance:
            from_wallet = from_asset.get_wallet(account, otc_request.market)
            from_wallet.has_balance(otc_request.get_paying_amount(), raise_exception=True, check_system_wallets=True)

        if otc_request.symbol.asset.otc_status not in (Asset.ACTIVE, otc_request.side):
            side_verbose = 'خرید' if otc_request.side == BUY else 'فروش'
            raise ValidationError('امکان %s این رمزارز وجود ندارد.' % side_verbose)

        otc_request.save()

        return otc_request

    @classmethod
    def get_otc_request(cls, account: Account, from_asset: Asset, to_asset: Asset, order_type: str,
                        from_amount: Decimal = None, to_amount: Decimal = None, market: str = Wallet.SPOT,
                        gtd: datetime = None, trigger_price: Decimal = None) -> 'OTCRequest':

        from market.models import PairSymbol
        assert order_type in cls.ORDER_TYPES
        assert (from_amount or to_amount) and (not from_amount or not to_amount), 'exactly one amount should present'

        pair = get_trading_pair(from_asset, to_asset, from_amount, to_amount)
        assert pair.base.symbol in (Asset.IRT, Asset.USDT)

        symbol = PairSymbol.objects.get(asset=pair.coin, base_asset=pair.base)

        otc_request = OTCRequest(
            account=account,
            from_asset=from_asset,
            to_asset=to_asset,
            market=market,
            from_amount=from_amount,
            to_amount=to_amount,
            symbol=symbol,
            side=pair.side,
            type=order_type,
            gtd=gtd,
            trigger_price=trigger_price
        )
        other_side = get_other_side(pair.side)
        coin_trigger_amount = 0

        usdt_irt_price = get_price(USDT_IRT, side=other_side, allow_stale=True)

        if pair.base.symbol == Asset.USDT:
            otc_request.base_usdt_price = 1
            otc_request.base_irt_price = usdt_irt_price
        else:
            otc_request.base_usdt_price = 1 / usdt_irt_price
            otc_request.base_irt_price = 1

        if pair.coin_amount is None:
            price = get_price(symbol.name, side=other_side)

            if price is None:
                raise NoPriceError

            if trigger_price:
                coin_trigger_amount = floor_precision(pair.base_amount / trigger_price, symbol.step_size)
            coin_amount = floor_precision(pair.base_amount / price, symbol.step_size)
        else:
            coin_trigger_amount = pair.coin_amount
            coin_amount = pair.coin_amount

        price = get_depth_price(symbol.name, side=other_side, amount=coin_amount)

        if price is None:
            raise NoPriceError

        if pair.coin_amount is None:
            if trigger_price:
                coin_trigger_amount = floor_precision(pair.base_amount / trigger_price, symbol.step_size)
            coin_amount = floor_precision(pair.base_amount / price, symbol.step_size)
        else:
            coin_trigger_amount = pair.coin_amount
            coin_amount = pair.coin_amount

        otc_request.amount = coin_amount if otc_request.type == OTCRequest.MARKET else coin_trigger_amount
        otc_request.price = price

        fee_info = get_fee_info(otc_request)

        otc_request.fee_amount = fee_info.trader_fee_amount
        otc_request.fee_usdt_value = fee_info.trader_fee_value
        otc_request.fee_revenue = fee_info.fee_revenue

        return otc_request

    def get_expire_time(self) -> datetime:
        return self.created + timedelta(seconds=OTCRequest.EXPIRATION_TIME)

    def get_receiving_amount(self):
        if self.side == SELL:
            price = self.price if self.type == OTCRequest.MARKET else self.trigger_price
            return self.amount * price
        else:
            return self.amount

    def get_paying_amount(self):
        if self.side == BUY:
            price = self.price if self.type == OTCRequest.MARKET else self.trigger_price
            return self.amount * price
        else:
            return self.amount

    def get_net_receiving_amount(self):
        return self.get_receiving_amount() - self.fee_amount

    def expired(self):
        return (timezone.now() - self.created).total_seconds() >= self.EXPIRATION_TIME

    def __str__(self):
        return f'{self.side} {get_presentation_amount(self.amount)} {self.symbol.asset} @' \
               f' {get_presentation_amount(self.price)} {self.symbol.base_asset}'

    class Meta:
        constraints = [
            CheckConstraint(check=Q(
                from_amount__gte=0,
                to_amount__gte=0,
            ), name='check_ledger_otc_request_amounts', ),

            CheckConstraint(check=Q(
                amount__gte=0,
                price__gte=0,
                fee_amount__gte=0,
            ), name='otc_request_check_trade_amounts', ),
        ]
