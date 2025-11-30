import logging
from collections import defaultdict
from decimal import Decimal
from typing import Union
from uuid import UUID

from django.db.models import Max, Min, F, Q, OuterRef, Subquery, DecimalField, Sum
from django.utils import timezone

from accounts.models import Account
from ledger.exceptions import InsufficientBalance
from ledger.models import Wallet, Asset
from ledger.utils.external_price import BUY, SELL
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import Order, PairSymbol, StopLoss
from market.models.order import CancelOrder
from market.utils.redis import MarketStreamCache

logger = logging.getLogger(__name__)


class MinTradeError(Exception):
    pass


class MaxTradeError(Exception):
    pass


class MinNotionalError(Exception):
    pass


def new_order(pipeline: WalletPipeline, symbol: PairSymbol, account: Account, side: str, amount: Decimal,
              price: Decimal = None, fill_type: str = Order.LIMIT, raise_exception: bool = True,
              market: str = Wallet.SPOT, order_type: str = Order.ORDINARY,
              parent_lock_group_id: Union[UUID, None] = None, stop_loss_id: Union[int, None] = None,
              time_in_force: str = Order.GTC, pass_min_notional: bool = False,
              variant: Union[str, None] = None, oco_id: Union[int, None] = None,
              client_order_id: str = None, margin_position=None) -> Union[Order, None]:

    assert price or fill_type == Order.MARKET

    wallet = symbol.asset.get_wallet(account, market=market, variant=variant)
    if fill_type == Order.MARKET:
        price = Order.get_market_price(symbol, Order.get_opposite_side(side))
        if not price:
            if raise_exception:
                raise Exception('Empty order book')
            else:
                logger.info('new order failed: empty order book %s' % symbol)
                return

    base_asset_symbol = symbol.base_asset.symbol

    if not pass_min_notional:
        if amount < symbol.min_trade_quantity:
            if raise_exception:
                raise MinTradeError
            else:
                logger.info(
                    'new order failed: min_trade_quantity %s (%s < %s)' % (symbol, amount, symbol.min_trade_quantity))
                return

        if amount > symbol.max_trade_quantity:
            if raise_exception:
                raise MinTradeError
            else:
                logger.info('new order failed: max_trade_quantity')
                return

        if base_asset_symbol == Asset.IRT:
            min_notional = Order.MIN_IRT_ORDER_SIZE
        elif base_asset_symbol == Asset.USDT:
            min_notional = Order.MIN_USDT_ORDER_SIZE
        else:
            raise NotImplementedError

        if amount * price < min_notional:
            if raise_exception:
                raise MinNotionalError
            else:
                logger.info('new order failed: min_notional')
                return

    additional_params = {'group_id': parent_lock_group_id} if parent_lock_group_id else {}
    if stop_loss_id:
        additional_params['stop_loss_id'] = stop_loss_id
    if oco_id:
        additional_params['oco_id'] = oco_id

    if margin_position:
        additional_params['position'] = margin_position

    order = Order.objects.create(
        account=account,
        wallet=wallet,
        symbol=symbol,
        amount=amount,
        price=price,
        side=side,
        fill_type=fill_type,
        type=order_type,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
        **additional_params
    )

    is_stop_loss = bool(additional_params.get('stop_loss_id'))
    is_oco = bool(additional_params.get('oco_id'))
    matched_trades = order.submit(pipeline, is_stop_loss=is_stop_loss, is_oco=is_oco)
    extra = {} if matched_trades.trade_pairs else {'side': order.side}
    pipeline.add_market_cache_data(symbol, matched_trades.filled_orders, trade_pairs=matched_trades.trade_pairs, **extra)

    if matched_trades and matched_trades.to_cancel_stoploss:
        from market.models import StopLoss
        StopLoss.objects.filter(id__in=map(lambda s: s.id, matched_trades.to_cancel_stoploss)).update(
            canceled_at=timezone.now()
        )

    order.trades = [p[0] for p in matched_trades.trade_pairs]
    return order


def trigger_stop_loss(pipeline: WalletPipeline, stop_loss: StopLoss, triggered_price: Decimal):
    try:
        if stop_loss.price:
            order = new_order(
                pipeline=pipeline,
                symbol=stop_loss.symbol,
                account=stop_loss.wallet.account,
                amount=stop_loss.unfilled_amount,
                price=stop_loss.price,
                side=stop_loss.side,
                fill_type=Order.LIMIT,
                raise_exception=False,
                market=stop_loss.wallet.market,
                parent_lock_group_id=stop_loss.group_id,
                stop_loss_id=stop_loss.id
            )
        else:
            order = new_order(
                pipeline=pipeline,
                symbol=stop_loss.symbol,
                account=stop_loss.wallet.account,
                amount=stop_loss.unfilled_amount,
                side=stop_loss.side,
                fill_type=Order.MARKET,
                raise_exception=False,
                market=stop_loss.wallet.market,
                parent_lock_group_id=stop_loss.group_id,
                stop_loss_id=stop_loss.id
            )
    except (InsufficientBalance, MinTradeError, MaxTradeError, MinNotionalError) as e:
        order = None
        logger.exception(f'exception on place order for stop loss ({stop_loss.symbol})', extra={
            'stop_loss': stop_loss.id,
            'exp': str(e),
        })
    if not order:
        logger.exception(f'could not place order for stop loss ({stop_loss.symbol})',
                         extra={
                             'triggered_price': triggered_price,
                             'stop_loss': stop_loss.id,
                             'stop_loss_side': stop_loss.side,
                             'stop_loss_trigger_price': stop_loss.trigger_price,
                         })
        if stop_loss.fill_type == StopLoss.MARKET and not stop_loss.canceled_at and \
                stop_loss.filled_amount < stop_loss.amount:
            return stop_loss
        return

    order.refresh_from_db()
    stop_loss.filled_amount += order.filled_amount
    stop_loss.save(update_fields=['filled_amount'])
    stop_loss.refresh_from_db()

    logger.info(f'filled order at {triggered_price} with amount: {order.filled_amount}, price: {order.price} for '
                f'stop loss({stop_loss.id}) {stop_loss.filled_amount} {stop_loss.trigger_price} {stop_loss.price} '
                f'{stop_loss.side} {timezone.now()}')
    if stop_loss.fill_type == StopLoss.MARKET and not stop_loss.canceled_at and \
            stop_loss.filled_amount < stop_loss.amount:
        return stop_loss


def get_market_top_prices(order_type='all', symbol_ids=None):
    market_top_prices = defaultdict(lambda: Decimal())
    symbol_filter = {'symbol_id__in': symbol_ids} if symbol_ids else {}
    if order_type != 'all':
        symbol_filter['type'] = order_type
    for depth in Order.open_objects.filter(**symbol_filter).values('symbol', 'side').annotate(
            max_price=Max('price'), min_price=Min('price')):
        market_top_prices[
            (depth['symbol'], depth['side'])
        ] = (depth['max_price'] if depth['side'] == BUY else depth['min_price']) or Decimal()
    return market_top_prices


def get_market_top_price_amounts(order_types_in=None, symbol_ids=None):
    market_top_price_amounts = defaultdict(lambda: {'price': Decimal(), 'amount': Decimal()})
    symbol_filter = {'symbol_id__in': symbol_ids} if symbol_ids else {}
    if order_types_in:
        symbol_filter['type__in'] = order_types_in
    sub_query = Order.open_objects.filter(
        **symbol_filter,
        symbol=OuterRef('symbol'),
        side=OuterRef('side'),
    )
    for depth in Order.open_objects.filter(**symbol_filter).values('symbol', 'side').annotate(
            min_price=Subquery(
                sub_query.order_by('price').values_list('price')[:1],
                output_field=DecimalField(),
            ),
            max_price=Subquery(
                sub_query.order_by('-price').values_list('price')[:1],
                output_field=DecimalField(),
            )
    ).filter(
        Q(price=F('max_price'), side=BUY) | Q(price=F('min_price'), side=SELL)
    ).annotate(total_amount=Sum('amount')):
        market_top_price_amounts[(depth['symbol'], depth['side'])] = {
            'price': depth['max_price'] if depth['side'] == BUY else depth['min_price'],
            'amount': depth['total_amount'],
        }
    return market_top_price_amounts
