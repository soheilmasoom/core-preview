import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone

from accounts.models import Referral, SystemConfig
from ledger.models import Wallet, Trx, Asset
from ledger.models.margin import REPAY, BORROW, OPEN
from ledger.models.position import MarginHistoryModel
from ledger.utils.cache import cache_for
from ledger.utils.external_price import BUY, SELL, LONG, SHORT
from ledger.utils.precision import floor_precision, get_symbol_presentation_price
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import Order, Trade, BaseTrade, PairSymbol
from market.models import ReferralTrx
from market.utils.price import get_symbol_prices

logger = logging.getLogger(__name__)


@dataclass
class FeeInfo:
    trader_fee_amount: Decimal = 0
    trader_fee_value: Decimal = 0
    referrer_reward_irt: Decimal = 0
    fee_revenue: Decimal = 0


@dataclass
class TradesPair:
    maker_trade: Trade
    taker_trade: Trade
    maker_order: Order
    taker_order: Order

    @property
    def trades(self):
        return [self.maker_trade, self.taker_trade]

    @classmethod
    def init_pair(cls, maker_order: Order, taker_order: Order, amount: Decimal, price: Decimal, trade_source: str,
                  base_irt_price: Decimal, base_usdt_price: Decimal, group_id: UUID):
        assert maker_order.symbol == taker_order.symbol

        maker_trade = Trade(
            symbol=maker_order.symbol,
            order_id=maker_order.id,
            account=maker_order.wallet.account,
            side=maker_order.side,
            is_maker=True,
            trade_source=trade_source,
            amount=amount,
            price=price,
            base_irt_price=base_irt_price,
            base_usdt_price=base_usdt_price,
            group_id=group_id,
            market=maker_order.wallet.market,
            login_activity=maker_order.login_activity,
            position=maker_order.position
        )

        taker_trade = Trade(
            symbol=maker_order.symbol,
            order_id=taker_order.id,
            account=taker_order.wallet.account,
            side=taker_order.side,
            is_maker=False,
            trade_source=trade_source,
            amount=amount,
            price=price,
            base_irt_price=base_irt_price,
            base_usdt_price=base_usdt_price,
            group_id=group_id,
            market=taker_order.wallet.market,
            login_activity=taker_order.login_activity,
            position=taker_order.position
        )
        maker_trade.client_order_id = maker_order.client_order_id
        taker_trade.client_order_id = taker_order.client_order_id

        return TradesPair(
            maker_trade=maker_trade,
            taker_trade=taker_trade,
            maker_order=maker_order,
            taker_order=taker_order,
        )


def _update_trading_positions(trading_positions, pipeline, trade_pair_list):
    from ledger.models import MarginPosition
    to_update_positions = {}
    for trade_info in trading_positions:
        position = to_update_positions.get(trade_info.position.id, trade_info.position)
        short_amount = trade_info.trade_amount if trade_info.loan_type in [BORROW, OPEN]\
            else -trade_info.trade_amount
        previous_amount, previous_price = position.amount, position.average_price
        position.amount += short_amount
        if short_amount > 0 and position.amount:
            position.average_price = (previous_amount * previous_price +
                                      short_amount * trade_info.trade_price) / position.amount

        total_match_amount = 0
        for trade_pair in trade_pair_list:
            total_match_amount += trade_pair.maker_trade.amount

        position_asset_wallet = position.asset_wallet
        position_asset_wallet.refresh_from_db()
        is_position_live = position.liquidation_price and (
                (position.side == SHORT and trade_info.trade_price < position.liquidation_price) or
                (position.side == LONG and trade_info.trade_price > position.liquidation_price))

        if (trade_info.loan_type not in [Order.LIQUIDATION, OPEN] and position.status == position.OPEN and
                trade_info.loan_type != Order.LIQUIDATION and
                (total_match_amount <= abs(position_asset_wallet.balance) * Decimal('0.998'))) and is_position_live:
            position.rebalance(pipeline, price=trade_info.trade_price)

        is_close_position = (trade_info.loan_type == Order.LIQUIDATION or
                             (floor_precision(position.asset_wallet.balance +
                                              pipeline.get_wallet_balance_diff(position.asset_wallet.id),
                                              position.symbol.step_size) >= Decimal('0') and
                              trade_info.loan_type != BORROW)) and \
                            floor_precision(position.loan_wallet.balance
                                            + pipeline.get_wallet_balance_diff(position.loan_wallet.id),
                                            position.symbol.step_size) >= Decimal('0')

        if is_close_position:
            logger.info(f"Closing position:{position.id}")
            position.convert_dust(pipeline)

            position.status = MarginPosition.CLOSED
            margin_cross_wallet = position.base_wallet.asset.get_wallet(
                position.account, market=Wallet.MARGIN, variant=None)

            position.base_wallet.refresh_from_db()
            remaining_balance = position.base_wallet.balance + pipeline.get_wallet_balance_diff(position.base_wallet.id)

            insurance_fee_amount = max(Decimal('0'), remaining_balance * SystemConfig.get_system_config().insurance_fee)
            if insurance_fee_amount > Decimal(0) and trade_info.loan_type == Order.LIQUIDATION:
                group_id = uuid4()
                pipeline.new_trx(
                    position.base_wallet,
                    position.get_insurance_wallet(),
                    insurance_fee_amount,
                    Trx.LIQUID,
                    group_id
                )
                position.create_history(
                    asset=position.symbol.base_asset,
                    amount=-insurance_fee_amount,
                    group_id=group_id,
                    type=MarginHistoryModel.INSURANCE_FEE
                )

            position.base_wallet.refresh_from_db()
            remaining_balance = position.base_wallet.balance + pipeline.get_wallet_balance_diff(position.base_wallet.id)

            if remaining_balance > Decimal('0'):
                group_id = uuid4()
                pipeline.new_trx(
                    position.base_wallet, margin_cross_wallet, remaining_balance, Trx.MARGIN_TRANSFER,
                    group_id
                )

                position.create_transfer_equity_history(
                    amount=remaining_balance,
                    debt_amount=position.debt_amount,
                    total_balance=position.total_balance,
                    group_id=group_id,
                    price=trade_info.trade_price
                )

        is_position_trade_beyond_liquidation = not is_position_live and trade_info.loan_type != OPEN
        if is_position_trade_beyond_liquidation:
            position.liquidate(pipeline, charge_insurance=True)
        
        if (is_position_live or trade_info.loan_type == OPEN) and not is_position_trade_beyond_liquidation:
            position.set_liquidation_price(pipeline)

        to_update_positions[position.id] = position

    MarginPosition.objects.bulk_update(
        to_update_positions.values(), ['amount', 'average_price', 'liquidation_price', 'status', 'equity']
    )


def register_transactions(pipeline: WalletPipeline, pair: TradesPair, fake_trade: bool = False, trade_pair_list=None):
    trading_positions = []
    if not fake_trade:
        trading_positions = _register_borrow_transaction(pipeline, pair=pair)
        _register_trade_transaction(pipeline, pair=pair)
        _register_trade_base_transaction(pipeline, pair=pair)

    taker_fee = register_fee_transactions(
        pipeline=pipeline,
        trade=pair.taker_trade,
        wallet=pair.taker_order.wallet,
        base_wallet=pair.taker_order.base_wallet,
        group_id=pair.taker_trade.group_id
    )

    pair.taker_trade.fee_amount = taker_fee.trader_fee_amount
    pair.taker_trade.fee_usdt_value = taker_fee.trader_fee_amount
    pair.taker_trade.fee_revenue = taker_fee.fee_revenue

    maker_fee = register_fee_transactions(
        pipeline=pipeline,
        trade=pair.maker_trade,
        wallet=pair.maker_order.wallet,
        base_wallet=pair.maker_order.base_wallet,
        group_id=pair.maker_trade.group_id
    )

    pair.maker_trade.fee_amount = maker_fee.trader_fee_amount
    pair.maker_trade.fee_usdt_value = maker_fee.trader_fee_amount
    pair.maker_trade.fee_revenue = maker_fee.fee_revenue

    if not fake_trade:
        trading_positions.extend(_register_repay_transaction(pipeline, pair=pair))
        _update_trading_positions(trading_positions, pipeline, trade_pair_list)


def _register_trade_transaction(pipeline: WalletPipeline, pair: TradesPair):
    if pair.maker_order.side == BUY:
        sender, receiver = pair.taker_order.wallet, pair.maker_order.wallet
    else:
        sender, receiver = pair.maker_order.wallet, pair.taker_order.wallet

    pipeline.new_trx(
        sender=sender,
        receiver=receiver,
        amount=pair.maker_trade.amount,
        group_id=pair.maker_trade.group_id,
        scope=Trx.TRADE
    )


def _register_margin_transaction(pipeline: WalletPipeline, pair: TradesPair, loan_type: str):
    if loan_type == BORROW:
        order_side = SELL
    elif loan_type == REPAY:
        order_side = BUY
    else:
        raise ValueError

    trade_price = pair.maker_trade.price
    trading_positions = []
    for order, trade in ((pair.maker_order, pair.maker_trade), (pair.taker_order, pair.taker_trade)):
        if order.wallet.market == Wallet.MARGIN:
            position = order.symbol.get_margin_position(order.account, order.side, order.is_open_position)
            if position.side == LONG:
                from ledger.utils.external_price import get_other_side
                order_side = get_other_side(order_side)

            if order.side == order_side:
                if (position.side == SHORT and order.is_open_position) or (position.side == LONG and not order.is_open_position):
                    trade_amount = trade.amount - trade.fee_amount if order_side == BUY else trade.amount
                else:
                    trade_amount = trade.amount - trade.fee_amount if order_side == SELL else trade.amount

                if not trade_amount:
                    continue
                trade_value = trade_price * trade_amount / order.get_position_leverage()
                if order.is_open_position:
                    margin_cross_wallet = order.base_wallet.asset.get_wallet(
                        order.base_wallet.account, market=order.base_wallet.market, variant=None
                    )
                    margin_cross_wallet.has_balance(
                        trade_value,
                        raise_exception=True,
                        pipeline_balance_diff=pipeline.get_wallet_free_balance_diff(margin_cross_wallet.id),
                    )
                    group_id = uuid4()
                    pipeline.new_trx(
                        group_id=group_id,
                        sender=margin_cross_wallet,
                        receiver=order.base_wallet,
                        amount=trade_value,
                        scope=Trx.MARGIN_TRANSFER
                    )
                    position.equity += trade_value

                order.symbol.get_margin_position(order.account, order.side, order.is_open_position)
                fee_amount = floor_precision(trade.fee_amount,
                                             Trade.fee_amount.field.decimal_places) if trade.fee_amount else Decimal(0)
                trade_amount = trade.amount - fee_amount if order_side == BUY else trade.amount
                if loan_type == REPAY:
                    trade_amount = min(position.amount, trade_amount)
                from ledger.models.position import MarginPositionTradeInfo
                loan_type = Order.LIQUIDATION if order.type == Order.LIQUIDATION else loan_type
                if order.is_open_position:
                    loan_type = OPEN
                trading_positions.append(MarginPositionTradeInfo(
                    loan_type=loan_type,
                    position=position,
                    trade_amount=trade_amount,
                    trade_price=trade_price,
                    group_id=order.group_id,
                    order_side=order.side
                ))
    return trading_positions


def _register_borrow_transaction(pipeline: WalletPipeline, pair: TradesPair):
    return _register_margin_transaction(pipeline, pair, BORROW)


def _register_repay_transaction(pipeline: WalletPipeline, pair: TradesPair):
    return _register_margin_transaction(pipeline, pair, REPAY)


def _register_trade_base_transaction(pipeline: WalletPipeline, pair: TradesPair):
    if pair.maker_order.side == SELL:
        sender, receiver = pair.taker_order.base_wallet, pair.maker_order.base_wallet
    else:
        sender, receiver = pair.maker_order.base_wallet, pair.taker_order.base_wallet

    pipeline.new_trx(
        sender=sender,
        receiver=receiver,
        amount=pair.maker_trade.amount * pair.maker_trade.price,
        group_id=pair.maker_trade.group_id,
        scope=Trx.TRADE
    )


def get_fee_info(trade: BaseTrade) -> FeeInfo:
    account = trade.account
    fee_rate = trade.symbol.get_fee_rate(account, trade.is_maker)

    if not fee_rate:
        return FeeInfo()

    referrer = account.referred_by
    base_amount = trade.amount * trade.price

    referrer_reward = 0
    trader_fee_rate = fee_rate
    system_fee_rate = fee_rate

    if referrer:
        referrer_share_percent = min(max(referrer.owner_share_percent, 0), 30)
        trader_share_percent = Referral.REFERRAL_MAX_RETURN_PERCENT - referrer_share_percent

        trader_fee_rate *= (1 - Decimal(trader_share_percent) / 100)
        referrer_reward = base_amount * fee_rate * Decimal(referrer_share_percent) / 100
        system_fee_rate *= (1 - Decimal(Referral.REFERRAL_MAX_RETURN_PERCENT) / 100)

    return FeeInfo(
        trader_fee_amount=trader_fee_rate * (trade.amount if trade.side == BUY else base_amount),
        trader_fee_value=trader_fee_rate * base_amount * trade.base_usdt_price,
        referrer_reward_irt=referrer_reward * trade.base_irt_price,
        fee_revenue=system_fee_rate * base_amount * trade.base_usdt_price,
    )


def register_fee_transactions(pipeline: WalletPipeline, trade: BaseTrade, wallet: Wallet, base_wallet: Wallet,
                              group_id: UUID) -> FeeInfo:
    account = trade.account
    referrer = account.referred_by
    fee_info = get_fee_info(trade)
    fee_payer = wallet if trade.side == BUY else base_wallet

    if fee_info.referrer_reward_irt:
        irt_asset = Asset.get(symbol=Asset.IRT)
        pipeline.new_trx(
            sender=irt_asset.get_wallet(settings.SYSTEM_ACCOUNT_ID, market=fee_payer.market),
            receiver=irt_asset.get_wallet(referrer.owner, Wallet.SPOT),
            amount=fee_info.referrer_reward_irt,
            group_id=group_id,
            scope=Trx.COMMISSION
        )
        ReferralTrx.objects.create(
            trader=wallet.account,
            referral=referrer,
            group_id=group_id,
            trader_amount=0,
            referrer_amount=fee_info.referrer_reward_irt
        )

    pipeline.new_trx(
        sender=fee_payer,
        receiver=fee_payer.asset.get_wallet(settings.SYSTEM_ACCOUNT_ID, market=fee_payer.market),
        amount=fee_info.trader_fee_amount,
        group_id=group_id,
        scope=Trx.COMMISSION
    )

    if fee_payer.market == fee_payer.MARGIN and isinstance(trade, Trade) and trade.position:
        trade.position.create_history(
            asset=fee_payer.asset,
            amount=-fee_info.trader_fee_amount,
            group_id=group_id,
            type=MarginHistoryModel.TRADE_FEE
        )

    return fee_info


def get_markets_price_info(base: str):
    prices = get_symbol_prices()
    recent_prices = prices['last']
    yesterday_prices = prices['yesterday']
    change_percents = {}

    symbol_id_map = {pair_symbol_id: [base_asset_name, coin, coin_name_fa]
                     for pair_symbol_id, base_asset_name, coin, coin_name_fa in
                     PairSymbol.objects.all().values_list('id', 'base_asset__symbol', 'asset__symbol', 'asset__name_fa')
                     }

    for pair_symbol_id in recent_prices.keys() & yesterday_prices.keys():
        if (recent_prices[pair_symbol_id] and yesterday_prices[pair_symbol_id]
                and symbol_id_map[pair_symbol_id][0] == base):

            yesterday_price = yesterday_prices[pair_symbol_id]
            recent_price = recent_prices[pair_symbol_id]
            change_24h = 100 * (recent_price - yesterday_price) // yesterday_price
            coin = symbol_id_map[pair_symbol_id][1]
            coin_name_fa = symbol_id_map[pair_symbol_id][2]

            change_percents[coin] = [coin_name_fa, recent_price, change_24h]

    return change_percents


def get_markets_size_ratio(base: str):
    markets_info = list(Trade.objects.filter(
        created__gte=timezone.now() - timedelta(days=1),
        symbol__base_asset__symbol=base
    ).values('symbol__asset__symbol')
                        .annotate(value=Sum(F('amount') * F('price'))).values_list('symbol__asset__symbol', 'value'))

    total_size = 0
    for coin, value in markets_info:
        total_size += value

    if total_size == Decimal(0):
        return {}

    for i in range(len(markets_info)):
        markets_info[i] = (markets_info[i][0], round(100 * markets_info[i][1] / total_size, 2))

    return markets_info


@cache_for(60 * 5)
def get_markets_info(base: str):
    markets_price_info = get_markets_price_info(base)

    market_ratios = get_markets_size_ratio(base)
    market_details = []

    for coin, ratio in market_ratios:
        if coin and ratio and markets_price_info.get(coin):
            name_fa = markets_price_info[coin][0]
            price = get_symbol_presentation_price(symbol=coin, amount=markets_price_info[coin][1])
            change_24h = markets_price_info[coin][2]

            market_details.append(
                {
                    'coin': coin,
                    'name_fa': name_fa,
                    'price': price,
                    'change_24h': change_24h,
                    'ratio': ratio,
                }
            )

    return market_details
