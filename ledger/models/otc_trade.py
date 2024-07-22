import logging
from decimal import Decimal
import os
from uuid import uuid4

from django.utils import timezone

from ledger.utils.price import get_depth_price, get_price


from django.conf import settings
from django.db import models
from django.db.models import F, Sum
from ledger.utils.external_price import BUY, SELL, get_other_side

from _base.settings import OTC_ACCOUNT_ID
from accounting.models import TradeRevenue
from accounts.models import Account, SystemConfig
from accounts.utils.admin import url_to_edit_object
from accounts.utils.telegram import send_system_message
from ledger.exceptions import HedgeError
from ledger.models import OTCRequest, Trx, Wallet, Asset
from ledger.utils.external_price import SELL, BUY
from ledger.utils.fields import get_amount_field
from ledger.utils.precision import floor_precision, get_symbol_presentation_price
from ledger.utils.revert import revert_trx_group
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import Trade, PairSymbol
from market.utils.order_utils import new_order
from market.utils.trade import register_fee_transactions

logger = logging.getLogger(__name__)


class TokenExpired(Exception):
    pass


class OTCTrade(models.Model):
    PENDING, CANCELED, USER_CANCELED, DONE, REVERT, EXPIRED = 'pending', 'canceled', 'user_canceled', 'done', 'revert', 'expired'
    MARKET, PROVIDER = 'm', 'p'

    created = models.DateTimeField(auto_now_add=True)
    otc_request = models.OneToOneField('ledger.OTCRequest', on_delete=models.PROTECT)

    group_id = models.UUIDField(default=uuid4, db_index=True)

    status = models.CharField(
        default=PENDING,
        max_length=16,
        choices=[(PENDING, PENDING), (CANCELED, CANCELED), (USER_CANCELED, USER_CANCELED), (DONE, DONE), (REVERT, REVERT), (EXPIRED, EXPIRED)],
    )

    execution_type = models.CharField(max_length=1, choices=((MARKET, 'market'), (PROVIDER, 'provider')))

    gap_revenue = get_amount_field(default=0)
    order_id = models.PositiveIntegerField(null=True, blank=True)
    to_buy_amount = get_amount_field(default=0, validators=())
    hedged = models.BooleanField(default=False, db_index=True)

    def change_status(self, status: str):
        self.status = status
        self.save(update_fields=['status'])

    def create_ledger(self, pipeline: WalletPipeline):
        user = self.otc_request.account

        from_asset = self.otc_request.from_asset
        to_asset = self.otc_request.to_asset

        pipeline.new_trx(
            sender=from_asset.get_wallet(user, market=self.otc_request.market),
            receiver=from_asset.get_wallet(OTC_ACCOUNT_ID, market=self.otc_request.market),
            amount=self.otc_request.get_paying_amount(),
            group_id=self.group_id,
            scope=Trx.TRADE
        )
        pipeline.new_trx(
            sender=to_asset.get_wallet(OTC_ACCOUNT_ID, market=self.otc_request.market),
            receiver=to_asset.get_wallet(user, market=self.otc_request.market),
            amount=self.otc_request.get_receiving_amount(),
            group_id=self.group_id,
            scope=Trx.TRADE
        )

    @property
    def client_order_id(self):
        return 'otc-%s' % self.id

    @classmethod
    def handle_otc_request(cls, otc_request: OTCRequest) -> 'OTCTrade':
        account = otc_request.account
        from_asset = otc_request.from_asset
        from_wallet = from_asset.get_wallet(account, market=otc_request.market)
        amount = otc_request.get_paying_amount()
        from_wallet.has_balance(amount, raise_exception=True)

        with WalletPipeline() as pipeline:
            otc_trade = OTCTrade.objects.create(
                otc_request=otc_request,
                execution_type=OTCTrade.MARKET,
                to_buy_amount=otc_request.amount if otc_request.side == BUY else -otc_request.amount,
                hedged=True
            )
            pipeline.new_lock(key=otc_trade.group_id, wallet=from_wallet, amount=amount,
                    reason=WalletPipeline.TRADE)

        if otc_trade:
            if otc_request.type == OTCRequest.LIMIT:
                return otc_trade
            return otc_trade.execute_trade()

    @classmethod
    def handle_expired(cls):
        query_set = cls.get_untriggered_otc_trade_queryset().filter(
            otc_request__gtd__lt=timezone.now())
        with WalletPipeline() as pipeline:
            for otc_trade in query_set:
                pipeline.release_lock(otc_trade.group_id)
            query_set.update(status=OTCTrade.EXPIRED)

    @classmethod
    def handle_trigger_price(cls, symbol: str, side: str, current_price: Decimal):
        def is_triggered_price(otc_request: OTCRequest) -> bool:
            current_price = get_depth_price(otc_request.symbol.name, side=get_other_side(otc_request.side), amount=otc_request.amount)
            trigger_price = otc_request.trigger_price
            side = otc_request.side
            if side == SELL and Decimal(current_price) * Decimal("0.8") < trigger_price < Decimal(current_price):
                return True
            elif side == BUY and Decimal(current_price) < trigger_price < Decimal(current_price) * Decimal("1.2"):
                return True
            return False

        triggered = cls.get_untriggered_otc_trade_queryset().filter(
            otc_request__symbol__name=symbol,
            otc_request__side=side,
            otc_request__gtd__gt=timezone.now(),
            otc_request__trigger_price__gte=Decimal(current_price) if side == BUY else Decimal(current_price) * Decimal("0.8"),
            otc_request__trigger_price__lte=Decimal(current_price) * Decimal("1.2") if side == BUY else Decimal(current_price)
        )

        print("triggered_requests:#", list(triggered))
        triggered_otc_trades = list(triggered)
        for triggered_otc_trade in triggered_otc_trades:
            if is_triggered_price(triggered_otc_trade.otc_request):
                triggered_otc_trade.execute_trade()

    @classmethod
    def get_untriggered_otc_trade_queryset(cls):
        result = OTCTrade.objects.filter(otc_request__type=OTCRequest.LIMIT, status=OTCTrade.PENDING).select_related('otc_request')
        print("untriggered_otc_trade:#",list(result))
        return result

    def execute_trade(self) -> 'OTCTrade':
        if self.otc_request.type == OTCRequest.MARKET and self.otc_request.expired():
            raise TokenExpired()

        with WalletPipeline() as pipeline:
            # todo: add lock when new engine deployed
            fok_success = self.try_fok_fill(pipeline)

            if not fok_success:
                if self.otc_request.symbol.enable and SystemConfig.get_system_config().hedge_coin_otc_from_internal_market:
                    logger.warning(f'Hedge otc from market failed in {self.otc_request.symbol}', extra={
                        'otc_request_id': self.otc_request.id
                    })
                    raise HedgeError
                self.execution_type = OTCTrade.PROVIDER
                self.hedged = False
                self.save(update_fields=['execution_type', 'hedged'])


        if not fok_success:
            self.try_provider_fill()

        return self

    def try_fok_fill(self, pipeline: WalletPipeline) -> bool:
        assert self.execution_type == self.MARKET

        symbol = self.otc_request.symbol
        if symbol.enable and SystemConfig.get_system_config().hedge_coin_otc_from_internal_market:
            from market.models import Order

            fok_order = new_order(
                pipeline=pipeline,
                symbol=symbol,
                account=Account.objects.get(id=OTC_ACCOUNT_ID),
                amount=self.otc_request.amount,
                price=self.otc_request.price,
                side=self.otc_request.side,
                time_in_force=Order.FOK,
                pass_min_notional=True,
                client_order_id=self.group_id
            )

            self.order_id = fok_order.id

            if fok_order.status == Order.FILLED:
                trades_base_sum = Trade.objects.filter(order_id=fok_order.id).aggregate(
                    sum=Sum(F('amount') * F('price'))
                )['sum'] or 0

                otc_base_amount = self.otc_request.amount * self.otc_request.price
                self.gap_revenue = (otc_base_amount - trades_base_sum) * self.otc_request.base_usdt_price
                if self.otc_request.side == SELL:
                    self.gap_revenue = -self.gap_revenue

                self.save(update_fields=['order_id', 'gap_revenue'])
                self.accept(pipeline)

                TradeRevenue.new(
                    user_trade=self.otc_request,
                    group_id=self.group_id,
                    source=TradeRevenue.OTC_MARKET,
                    hedge_key=str(fok_order.id),
                ).save()

                return True
            else:
                self.save(update_fields=['order_id'])

        return False

    def try_provider_fill(self):

        try:
            self.hedge_with_provider()
        except (HedgeError):
            logger.exception('Error in hedging otc request')
            self.cancel()
            raise

    def cancel(self, is_user_request=False):
        with WalletPipeline() as pipeline:  # type: WalletPipeline
            pipeline.release_lock(self.group_id)
            self.change_status(self.USER_CANCELED) if is_user_request else self.change_status(self.CANCELED)

    def accept(self, pipeline: WalletPipeline):
        pipeline.release_lock(self.group_id)

        self.change_status(self.DONE)
        self.create_ledger(pipeline)

        register_fee_transactions(
            pipeline=pipeline,
            trade=self.otc_request,
            wallet=self.otc_request.symbol.asset.get_wallet(self.otc_request.account),
            base_wallet=self.otc_request.symbol.base_asset.get_wallet(self.otc_request.account),
            group_id=self.group_id
        )

        # updating trade_volume_irt of accounts
        account = self.otc_request.account
        account.trade_volume_irt = F('trade_volume_irt') + self.otc_request.irt_value
        account.save(update_fields=['trade_volume_irt'])
        account.refresh_from_db()

        from gamify.utils import check_prize_achievements, Task
        check_prize_achievements(account, Task.TRADE)

        req = self.otc_request

        if not req.symbol.asset.hedge and req.symbol.asset.symbol != Asset.USDT:
            amount_present = get_symbol_presentation_price(req.symbol.name, req.amount, trunc_zero=True)

            send_system_message(
                message=f"New unhedged trade: {req.side} {amount_present} {req.symbol.asset} ({round(req.usdt_value, 1)}$)",
                link=url_to_edit_object(self)
            )

    def get_pending_hedge_trades(self):
        return OTCTrade.objects.filter(
            otc_request__symbol__asset=self.otc_request.symbol.asset,
            hedged=False,
            status=OTCTrade.DONE,
        )

    def get_pending_to_buy_amount(self):
        return self.get_pending_hedge_trades().aggregate(
            to_buy=Sum('to_buy_amount')
        )['to_buy'] or Decimal(0)

    def hedge_with_provider(self, hedge: bool = True):
        assert self.execution_type == self.PROVIDER

        with WalletPipeline() as pipeline:  # type: WalletPipeline
            self.accept(pipeline)
            hedge_key = ''

            if hedge:
                req = self.otc_request
                _key = 'otc:%s' % self.id

                hedge_price = None
                buy_amount = self.get_pending_to_buy_amount()

                if buy_amount != 0 and self.to_buy_amount / buy_amount > Decimal('0.9'):
                    hedge_price = req.price * req.base_usdt_price

                from ledger.utils.provider import TRADE, get_provider_requester
                hedged = get_provider_requester().try_hedge_new_order(
                    request_id=_key,
                    asset=req.symbol.asset,
                    buy_amount=buy_amount,
                    scope=TRADE,
                    hedge_price=hedge_price
                )

                if SystemConfig.get_system_config().hedge_irt_by_internal_market and req.symbol.name != 'USDTIRT' and req.symbol.base_asset.symbol == Asset.IRT:
                    from market.models import Order
                    usdt_irt = PairSymbol.objects.get(name='USDTIRT')

                    amount = floor_precision(req.usdt_value, usdt_irt.step_size)

                    order = new_order(
                        pipeline=pipeline,
                        symbol=usdt_irt,
                        account=Account.objects.get(id=OTC_ACCOUNT_ID),
                        side=req.side,
                        amount=amount,
                        fill_type=Order.MARKET,
                        raise_exception=False
                    )
                    if order and order.trades:
                        filled_amount = sum(map(lambda t: t.amount, order.trades))
                        if filled_amount:
                            filled_value = sum(map(lambda t: t.amount * t.price, order.trades))
                            filled_price = filled_value / filled_amount
                            self.otc_request.base_usdt_price = 1 / filled_price

                if hedged:
                    hedge_key = _key

                if hedged or not req.symbol.asset.hedge:
                    self.get_pending_hedge_trades().update(hedged=True)

            from accounting.models.revenue import TradeRevenue
            TradeRevenue.new(
                user_trade=self.otc_request,
                group_id=self.group_id,
                source=TradeRevenue.OTC_PROVIDER,
                hedge_key=hedge_key,
            ).save()

    def revert(self):
        with WalletPipeline() as pipeline:
            self.status = self.REVERT
            self.save(update_fields=['status'])
            revert_trx_group(pipeline, self.group_id)

            from market.models import Trade
            Trade.objects.filter(group_id=self.group_id).update(status=Trade.REVERT)

    def __str__(self):
        return '%s [%s]' % (self.otc_request, self.status)
