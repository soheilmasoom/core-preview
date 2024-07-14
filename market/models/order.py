import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
from math import floor, log10
from typing import Union
from uuid import uuid4

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q, Max, Min, CheckConstraint, QuerySet, Sum, UniqueConstraint
from django.utils import timezone

from accounting.models import TradeRevenue
from accounts.models import Notification
from accounts.models import SystemConfig
from ledger.models import Wallet
from ledger.models.asset import Asset
from ledger.models.balance_lock import BalanceLock
from ledger.utils.external_price import BUY, SELL, SIDE_VERBOSE
from ledger.utils.fields import get_amount_field, get_group_id_field
from ledger.utils.precision import floor_precision, decimal_to_str
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol, BaseTrade
from market.utils.price import set_last_trade_price

logger = logging.getLogger(__name__)


@dataclass
class MatchedTrades:
    trades: list = None
    trade_pairs: list = None
    filled_orders: list = None
    to_cancel_stoploss: list = None

    def __post_init__(self):
        if self.trades is None:
            self.trades = []
        if self.trade_pairs is None:
            self.trade_pairs = []
        if self.filled_orders is None:
            self.filled_orders = []
        if self.to_cancel_stoploss is None:
            self.to_cancel_stoploss = []

    def __bool__(self):
        return bool(self.trades and self.trade_pairs)


@dataclass
class TopOrder:
    side: str
    price: Decimal
    amount: Decimal


class OpenOrderManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Order.NEW)


class CancelOrder(Exception):
    pass


class Order(models.Model):
    MARKET_BORDER = Decimal('1e-2')
    MIN_IRT_ORDER_SIZE = Decimal('1e5')
    MIN_USDT_ORDER_SIZE = Decimal(5)
    MAX_ORDER_DEPTH_SIZE_IRT = Decimal('9e7')
    MAX_ORDER_DEPTH_SIZE_USDT = Decimal(2500)
    MAKER_ORDERS_COUNT = 10 if settings.DEBUG_OR_TESTING else 50

    LIMIT, MARKET = 'limit', 'market'
    FILL_TYPE_CHOICES = [(LIMIT, LIMIT), (MARKET, MARKET)]

    TIME_IN_FORCE_OPTIONS = GTC, FOK, IOC, ME_IOC = None, 'FOK', 'IOC', 'ME_IOC'

    NEW, CANCELED, FILLED = 'new', 'canceled', 'filled'
    STATUS_CHOICES = [(NEW, NEW), (CANCELED, CANCELED), (FILLED, FILLED)]

    DEPTH = 'depth'
    BOT = 'bot'
    ORDINARY = None
    LIQUIDATION = 'liquid'

    TYPE_CHOICES = ((DEPTH, 'depth'), (BOT, 'bot'), (ORDINARY, 'ordinary'), (LIQUIDATION, LIQUIDATION))

    type = models.CharField(
        max_length=8,
        choices=TYPE_CHOICES,
        null=True,
        blank=True
    )

    created = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey('accounts.Account', on_delete=models.PROTECT)
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='orders')

    symbol = models.ForeignKey(PairSymbol, on_delete=models.PROTECT)
    amount = get_amount_field()
    filled_amount = get_amount_field(default=Decimal(0))
    price = get_amount_field()
    side = models.CharField(max_length=8, choices=BaseTrade.SIDE_CHOICES)
    fill_type = models.CharField(max_length=8, choices=FILL_TYPE_CHOICES)
    status = models.CharField(default=NEW, max_length=8, choices=STATUS_CHOICES)

    group_id = get_group_id_field(null=True)

    client_order_id = models.CharField(max_length=36, null=True, blank=True)

    stop_loss = models.ForeignKey(to='market.StopLoss', on_delete=models.SET_NULL, null=True, blank=True)
    oco = models.ForeignKey(to='market.OCO', on_delete=models.SET_NULL, null=True, blank=True)

    is_open_position = models.BooleanField(null=True, default=None)
    position = models.ForeignKey(to='ledger.MarginPosition', on_delete=models.CASCADE, null=True)

    time_in_force = models.CharField(
        max_length=6,
        blank=True,
        null=True,
        choices=[(GTC, 'GTC'), (FOK, 'FOK'), (IOC, 'IOC'), (ME_IOC, 'ME_IOC')]
    )
    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'({self.id}) {self.symbol}-{self.side} [p:{self.price:.2f}] (u:{self.unfilled_amount:.5f}/{self.amount:.5f})'

    class Meta:
        ordering = ['status']
        indexes = [
            models.Index(fields=['symbol', 'type', 'status', 'created']),
            models.Index(fields=['symbol', 'status']),
            models.Index(name='market_new_orders_price_idx', fields=['price'], condition=Q(status='new')),
        ]
        constraints = [
            CheckConstraint(check=Q(filled_amount__lte=F('amount')), name='check_filled_amount', ),
            CheckConstraint(check=Q(amount__gte=0, filled_amount__gte=0, price__gte=0),
                            name='check_market_order_amounts', ),
            UniqueConstraint(
                fields=('account', 'client_order_id', 'status'),
                condition=Q(status='new'),
                name='unique_client_order_id_new_order'
            ),
            UniqueConstraint(
                name='market_order_unique_group_id',
                fields=('group_id', 'status'),
            ),
            UniqueConstraint(
                name='market_order_unique_stop_loss',
                fields=('stop_loss', 'status'),
            ),
            UniqueConstraint(
                name='market_order_unique_oco',
                fields=('oco', 'status'),
            ),
        ]

    objects = models.Manager()
    open_objects = OpenOrderManager()

    def cancel(self):
        if self.oco:
            self.oco.cancel_another(self.oco.STOPLOSS, delete_oco=True)

        # to increase performance
        if self.status != self.NEW:
            return

        with WalletPipeline() as pipeline:  # type: WalletPipeline
            PairSymbol.objects.select_for_update().get(id=self.symbol_id)
            order = Order.objects.filter(status=Order.NEW, id=self.id).first()

            if not order:
                return

            order.status = self.CANCELED
            order.save(update_fields=['status'])
            pipeline.release_lock(key=order.group_id)

            pipeline.add_market_cache_data(self.symbol, [order], side=order.side, canceled=True)

    @classmethod
    def bulk_cancel_simple_orders(cls, to_cancel_orders: QuerySet):
        orders = list(to_cancel_orders.filter(oco__isnull=True, status=cls.NEW).values('id', 'symbol_id'))

        with WalletPipeline() as pipeline:  # type: WalletPipeline
            list(PairSymbol.objects.select_for_update().filter(id__in=[o['symbol_id'] for o in orders]))
            orders = Order.open_objects.filter(id__in=[o['id'] for o in orders]).only('group_id', 'id')  # to sync with symbol lock

            ids = []
            for order in orders:
                ids.append(order.id)
                pipeline.release_lock(key=order.group_id)
                pipeline.add_market_cache_data(order.symbol, [order], side=order.side, canceled=True)

            orders.update(status=cls.CANCELED)

            from market.models import CancelRequest

            cancel_requests = []
            ids = set(ids).difference(set(CancelRequest.objects.filter(order_id__in=ids).values_list('order_id', flat=True)))

            for _id in ids:
                cancel_requests.append(
                    CancelRequest(order_id=_id)
                )
            CancelRequest.objects.bulk_create(cancel_requests)

    @property
    def base_wallet(self):
        _base_wallet = getattr(self, '_base_wallet', None)

        if not _base_wallet:
            _base_wallet = self.symbol.base_asset.get_wallet(
                account=self.wallet.account, market=self.wallet.market, variant=self.wallet.variant
            )
            setattr(self, '_base_wallet', _base_wallet)

        return _base_wallet

    @property
    def unfilled_amount(self):
        amount = self.amount - self.filled_amount
        return floor_precision(amount, self.symbol.step_size)

    @staticmethod
    def get_opposite_side(side):
        return SELL if side.lower() == BUY else BUY

    @staticmethod
    def get_order_by(side):
        return (lambda order: (-order.price, order.id)) if side == BUY else \
            (lambda order: (order.price, order.id))

    @classmethod
    def cancel_orders(cls, to_cancel_orders: QuerySet):
        # for order in to_cancel_orders.filter(status=Order.NEW):
        for order in to_cancel_orders:
            order.cancel()

    @staticmethod
    def get_price_filter(price, side):
        return {'price__lte': price} if side == BUY else {'price__gte': price}

    @staticmethod
    def get_position(account, symbol):
        from ledger.models import MarginPosition
        return MarginPosition.objects.filter(
            account=account, symbol=symbol, status__in=[MarginPosition.OPEN, MarginPosition.TERMINATING]
        ).first()

    @staticmethod
    def get_to_lock_wallet(wallet, base_wallet, side, symbol, is_open_position: bool = False) -> Wallet:
        if wallet.market == Wallet.MARGIN:
            if is_open_position:
                margin_cross_wallet = base_wallet.asset.get_wallet(
                    base_wallet.account, market=base_wallet.market, variant=None
                )
                return margin_cross_wallet
            else:
                from ledger.models import MarginPosition

                position = MarginPosition.get_by(
                    account=wallet.account, symbol=symbol, is_open_position=is_open_position, order_side=side
                )

                return position.base_wallet if side == BUY else position.asset_wallet

        return base_wallet if side == BUY else wallet

    @classmethod
    def get_to_lock_amount(cls, amount: Decimal, price: Decimal, side: str, market, is_open_position: bool = False, leverage: int = None) -> Decimal:
        if market == Wallet.MARGIN and is_open_position:
            assert leverage

            return amount * price / leverage
        return amount * price if side == BUY else amount

    def get_position_leverage(self):
        if self.wallet.market == Wallet.MARGIN:
            return self.symbol.get_margin_position(self.account, self.side, self.is_open_position).leverage
        return None

    def handle_oco_updates(self, pipeline):
        self.oco.cancel_another(self.oco.STOPLOSS)

        if self.side == BUY and self.oco.releasable_lock:
            oco = self.oco
            pipeline.release_lock(key=self.group_id, amount=oco.releasable_lock)
            oco.releasable_lock = Decimal(0)
            oco.save(update_fields=['releasable_lock'])

    def submit(self, pipeline: WalletPipeline, is_stop_loss: bool = False, is_oco: bool = False, is_open_position: bool = None) -> MatchedTrades:
        PairSymbol.objects.select_for_update().get(id=self.symbol_id)
        overriding_fill_amount = None

        if is_stop_loss:
            if self.side == BUY:
                locked_amount = BalanceLock.objects.get(key=self.group_id).amount
                if locked_amount < self.amount * self.price:
                    overriding_fill_amount = floor_precision(locked_amount / self.price, self.symbol.step_size)
                    if not overriding_fill_amount:
                        raise CancelOrder('Overriding fill amount is zero')

        elif not is_oco:
            overriding_fill_amount = self.acquire_lock(pipeline, is_open_position=is_open_position)

        matched_trades = self.make_match(pipeline, overriding_fill_amount)
        if matched_trades:
            min_price = min(map(lambda t: t.price, matched_trades.trades))
            max_price = max(map(lambda t: t.price, matched_trades.trades))
            from market.models import StopLoss
            StopLoss.trigger(self, min_price, max_price, matched_trades, pipeline)
            from ledger.models import MarginPosition
            MarginPosition.check_for_liquidation(self, min_price, max_price, pipeline)

        return matched_trades

    def acquire_lock(self, pipeline: WalletPipeline, is_open_position: bool = None):
        lock_amount = Order.get_to_lock_amount(self.amount, self.price, self.side, self.wallet.market, is_open_position,
                                               self.get_position_leverage())
        to_lock_wallet = Order.get_to_lock_wallet(self.wallet, self.base_wallet, self.side, self.symbol,
                                                  is_open_position)

        if self.side == BUY and self.fill_type == Order.MARKET and self.wallet.market != Wallet.MARGIN:
            free_amount = to_lock_wallet.get_free()
            if free_amount > Decimal('0.95') * lock_amount:
                lock_amount = min(lock_amount, free_amount)

        to_lock_wallet.has_balance(
            lock_amount,
            raise_exception=True,
            pipeline_balance_diff=pipeline.get_wallet_free_balance_diff(to_lock_wallet.id)
        )

        pipeline.new_lock(key=self.group_id, wallet=to_lock_wallet, amount=lock_amount, reason=WalletPipeline.TRADE)

        if self.side == BUY and self.fill_type == Order.MARKET:
            return floor_precision(self.get_overriding_fill_amount(lock_amount), self.symbol.step_size)

    def get_overriding_fill_amount(self, lock_amount):  # todo :: for god's sake delete this shit
        overriding_fill_amount = lock_amount / self.price
        if self.wallet.market == self.wallet.MARGIN:
            # only LONG POSITION Accepted
            if self.is_open_position:
                overriding_fill_amount *= self.get_position_leverage()
            else:
                overriding_fill_amount = Decimal('0')
        return overriding_fill_amount

    def release_lock(self, pipeline: WalletPipeline, release_amount: Decimal):
        release_amount = Order.get_to_lock_amount(release_amount, self.price, self.side, self.wallet.market,
                                                  is_open_position=self.is_open_position,
                                                  leverage=self.get_position_leverage())
        pipeline.release_lock(key=self.group_id, amount=release_amount)

    def make_match(self, pipeline: WalletPipeline, overriding_fill_amount: Union[Decimal, None]) -> MatchedTrades:
        from market.utils.trade import register_transactions, TradesPair
        from market.models import Trade
        from ledger.utils.price import get_last_price, USDT_IRT

        symbol = self.symbol

        log_prefix = 'MM %s {%s}: ' % (symbol.name, self.id)

        logger.info(log_prefix + f'make match started... {overriding_fill_amount} {timezone.now()}')

        maker_side = self.get_opposite_side(self.side)

        matching_orders = Order.open_objects.filter(symbol=symbol, side=maker_side).prefetch_related('wallet__account')
        if maker_side == BUY:
            matching_orders = matching_orders.filter(price__gte=self.price).order_by('-price', 'id')
        else:
            matching_orders = matching_orders.filter(price__lte=self.price).order_by('price', 'id')

        unfilled_amount = overriding_fill_amount or self.unfilled_amount

        if self.time_in_force == self.FOK:
            total_maker_amounts = matching_orders.aggregate(
                total_amount=Sum(F('amount') - F('filled_amount'))
            )['total_amount'] or 0

            if unfilled_amount > total_maker_amounts:
                self.status = Order.CANCELED
                pipeline.release_lock(self.group_id)
                self.save(update_fields=['status'])
                return MatchedTrades()

        matching_orders = list(matching_orders)
        logger.info(log_prefix + f'make match finished fetching matching orders {len(matching_orders)} {timezone.now()}')

        if not matching_orders:
            if (self.fill_type == Order.MARKET or self.time_in_force in [self.IOC, self.ME_IOC]) and self.status == Order.NEW:
                self.status = Order.CANCELED
                pipeline.release_lock(self.group_id)
                self.save(update_fields=['status'])
            return MatchedTrades()

        trades = []
        filled_orders = []

        tether_irt = get_last_price(USDT_IRT)

        oco_orders = [self] if self.oco else []

        total_matched = 0
        trade_pair_list = []

        for maker_order in matching_orders:
            if self.time_in_force == self.ME_IOC and maker_order.account != self.account:
                break

            trade_price = maker_order.price

            match_amount = min(maker_order.unfilled_amount, unfilled_amount)
            if match_amount <= 0:
                continue

            total_matched += match_amount

            base_irt_price = 1
            base_usdt_price = 1

            if symbol.base_asset.symbol == Asset.USDT:
                base_irt_price = tether_irt
            else:
                base_usdt_price = 1 / tether_irt

            trades_pair = TradesPair.init_pair(
                taker_order=self,
                maker_order=maker_order,
                amount=match_amount,
                price=trade_price,
                base_irt_price=base_irt_price,
                base_usdt_price=base_usdt_price,
                trade_source=Trade.MARKET,
                group_id=uuid4()
            )
            trade_pair_list.append(trades_pair)

            if not maker_order.wallet.account.is_system():
                Notification.send(
                    recipient=maker_order.wallet.account.user,
                    title='معامله {} انجام شد'.format(maker_order.symbol),
                    message='{side} {amount} {coin}'.format(
                        amount=match_amount,
                        side=SIDE_VERBOSE[maker_side],
                        coin=symbol.asset.name_fa
                    )
                )

            self.release_lock(pipeline, match_amount)
            maker_order.release_lock(pipeline, match_amount)

            register_transactions(pipeline, pair=trades_pair, trade_pair_list=trade_pair_list)

            trades.extend(trades_pair.trades)

            self.update_filled_amount((self.id, maker_order.id), match_amount)

            unfilled_amount -= match_amount
            if match_amount == maker_order.unfilled_amount:  # unfilled_amount reduced in DB but not updated here :)
                with transaction.atomic():
                    maker_order.status = Order.FILLED
                    maker_order.save(update_fields=['status'])
                    filled_orders.append(maker_order)

            if maker_order.oco:
                oco_orders.append(maker_order)

            if unfilled_amount == 0:
                self.status = Order.FILLED

                if self.fill_type == Order.MARKET:
                    pipeline.release_lock(self.group_id)

                self.save(update_fields=['status'])
                break

        if total_matched > 0 and not self.wallet.account.is_system():
            Notification.send(
                recipient=self.wallet.account.user,
                title='معامله {} انجام شد'.format(symbol),
                message='{side} {amount} {coin}'.format(
                    amount=total_matched,
                    side=SIDE_VERBOSE[self.side],
                    coin=symbol.asset.name_fa
                )
            )

        if (self.fill_type == Order.MARKET or self.time_in_force in [self.IOC, self.ME_IOC]) and self.status == Order.NEW:
            self.status = Order.CANCELED
            pipeline.release_lock(self.group_id)
            self.save(update_fields=['status'])

        trades = Trade.objects.bulk_create(trades)
        trade_pairs = list(zip(trades[0::2], trades[1::2]))

        if trades:
            symbol.last_trade_time = timezone.now()
            symbol.last_trade_price = trades[-1].price
            symbol.save(update_fields=['last_trade_time', 'last_trade_price'])
            set_last_trade_price(symbol)

            for oco_order in oco_orders:
                oco_order.handle_oco_updates(pipeline)

            self.create_trade_revenues(trade_pairs)

        # updating trade_volume_irt of accounts
        for trade in trades:
            account = trade.account
            if not account.is_system():
                account.trade_volume_irt = F('trade_volume_irt') + trade.irt_value
                account.save(update_fields=['trade_volume_irt'])
                account.refresh_from_db()

                from gamify.utils import check_prize_achievements, Task
                check_prize_achievements(account, Task.TRADE)

        logger.info(log_prefix + f'make match finished.  {timezone.now()}')
        return MatchedTrades(trades=trades, trade_pairs=trade_pairs, filled_orders=filled_orders)

    @classmethod
    def get_formatted_orders(cls, open_orders, symbol: PairSymbol, order_type: str):
        filtered_orders = list(filter(lambda o: o['side'] == order_type, open_orders))
        aggregated_orders = cls.get_aggregated_orders(symbol, *filtered_orders)

        sort_func = (lambda o: -Decimal(o['price'])) if order_type == BUY else (lambda o: Decimal(o['price']))

        return sorted(aggregated_orders, key=sort_func)

    @staticmethod
    def get_aggregated_orders(symbol: PairSymbol, *orders):
        key_func = (lambda o: o['price'])
        grouped_by_price = [(i[0], list(i[1])) for i in groupby(sorted(orders, key=key_func), key=key_func)]
        return [{
            'price': format(price, 'f'),
            'amount': decimal_to_str(floor_precision(sum(map(lambda i: i['unfilled_amount'], price_orders)), symbol.step_size)),
            'depth': Order.get_depth_value(sum(map(lambda i: i['unfilled_amount'], price_orders)), price,
                                           symbol.base_asset.symbol),
            'total': decimal_to_str(floor_precision(sum(map(lambda i: i['unfilled_amount'] * price, price_orders)), 0))
        } for price, price_orders in grouped_by_price]

    @staticmethod
    def get_depth_value(amount, price, base_asset: str):
        if base_asset == Asset.IRT:
            return str(min(100, floor_precision((amount * price) / Order.MAX_ORDER_DEPTH_SIZE_IRT * 100, 0)))
        if base_asset == Asset.USDT:
            return str(min(100, floor_precision((amount * price) / Order.MAX_ORDER_DEPTH_SIZE_USDT * 100, 0)))

    @staticmethod
    def quantize_values(symbol: PairSymbol, open_orders):
        return [{
            'side': order['side'],
            'price': floor_precision(order['price'], symbol.tick_size),
            'unfilled_amount': floor_precision(order['unfilled_amount'], symbol.step_size),
        } for order in open_orders]

    # Market Maker related methods
    @staticmethod
    def get_rounding_precision(number, max_precision):
        power = floor(log10(number))
        precision = min(3, -power / 3) if power > 2 else (2 - power)
        return int(min(precision, max_precision))

    @classmethod
    def update_filled_amount(cls, order_ids, match_amount):
        Order.objects.filter(id__in=order_ids).update(filled_amount=F('filled_amount') + match_amount)
        from market.models import StopLoss
        StopLoss.objects.filter(order__id__in=order_ids).update(filled_amount=F('filled_amount') + match_amount)

    @classmethod
    def get_market_price(cls, symbol, side):
        open_orders = Order.open_objects.filter(symbol_id=symbol.id, side=side, fill_type=Order.LIMIT)
        top_order = open_orders.aggregate(top_price=Max('price')) if side == BUY else \
            open_orders.aggregate(top_price=Min('price'))
        if not top_order['top_price']:
            return
        market_price = top_order['top_price'] * (Decimal(1) - cls.MARKET_BORDER) if side == BUY else \
            top_order['top_price'] * (Decimal(1) + cls.MARKET_BORDER)
        return market_price

    @classmethod
    def get_top_depth_prices(cls, symbol_id, scope=''):
        from market.utils.redis import get_top_prices
        top_prices = get_top_prices(symbol_id, scope=scope)
        if not top_prices:
            top_prices = defaultdict(lambda: Decimal())
            for depth in Order.open_objects.filter(symbol_id=symbol_id, type=Order.DEPTH).values('side').annotate(
                    max_price=Max('price'), min_price=Min('price')
            ):
                top_prices[depth['side']] = (depth['max_price'] if depth['side'] == BUY else depth['min_price']) \
                                            or Decimal()
        return top_prices

    @classmethod
    def get_top_price(cls, symbol_id, side):
        agg_func = Max if side == BUY else Min
        top_price = cls.open_objects.filter(
            symbol_id=symbol_id, side=side
        ).aggregate(top_price=agg_func('price'))['top_price']
        return top_price

    @classmethod
    def get_top_price_amount(cls, symbol_id, side):
        agg_func = Max if side == BUY else Min
        top_price = cls.open_objects.filter(
            symbol_id=symbol_id, side=side
        ).aggregate(top_price=agg_func('price'))['top_price']
        if not top_price:
            return None
        unfilled_amount = cls.open_objects.filter(
            symbol_id=symbol_id, side=side, price=top_price
        ).annotate(unfilled_amount=F('amount') - F('filled_amount')).aggregate(
            total_amount=Sum('unfilled_amount')
        )['total_amount']
        return TopOrder(side=side, price=top_price, amount=unfilled_amount)

    def create_trade_revenues(self, trade_pairs: list):
        from ledger.utils.price import USDT_IRT

        symbol = self.symbol

        taker_is_proxy = self.wallet.account.is_proxy_trader(symbol.name)

        trade_revenues = []
        for maker_trade, taker_trade in trade_pairs:
            maker_is_proxy = maker_trade.account.is_proxy_trader(symbol.name)
            any_proxy = taker_is_proxy or maker_is_proxy

            if symbol.name == USDT_IRT:
                if SystemConfig.get_system_config().hedge_irt_by_internal_market:
                    hedger_account_id = settings.TRADER_ACCOUNT_ID
                    hedger_prefix = 'tr'
                else:
                    hedger_account_id = settings.MARKET_MAKER_ACCOUNT_ID
                    hedger_prefix = ''
            else:
                hedger_account_id = settings.MARKET_MAKER_ACCOUNT_ID
                hedger_prefix = 'mm'

            trades = sorted(
                [maker_trade, taker_trade],
                key=lambda _t: _t.account_id == hedger_account_id,
                reverse=True
            )

            any_non_system_trade = bool(
                {maker_trade.account_id, taker_trade.account_id} -
                {settings.TRADER_ACCOUNT_ID, settings.MARKET_MAKER_ACCOUNT_ID}
            )

            if any_non_system_trade:
                if trades[0].account_id != hedger_account_id:
                    for t in trades:
                        trade_revenues.append(
                            TradeRevenue.new(
                                user_trade=t,
                                group_id=t.group_id,
                                source=TradeRevenue.USER,
                                hedge_key='',
                                ignore_trade_value=any_proxy or (t == maker_trade)
                            )
                        )

                elif trades[0].account_id != trades[1].account_id:
                    if hedger_prefix:
                        # taker = trades[1] if trades[0].is_maker else trades[0]
                        hedge_key = f'{hedger_prefix}-{trades[0].id}'
                    else:
                        hedge_key = ''

                    trade = trades[1]

                    trade_revenues.append(TradeRevenue.new(
                        user_trade=trade,
                        group_id=trade.group_id,
                        source=TradeRevenue.MAKER if trades[0].is_maker else TradeRevenue.TAKER,
                        hedge_key=hedge_key,
                        ignore_trade_value=any_proxy
                    ))

        if trade_revenues:
            TradeRevenue.objects.bulk_create(trade_revenues)
