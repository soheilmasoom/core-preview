import logging
import random

from celery import shared_task
from django.db.models import Q

from _base.settings import TRADER_ACCOUNT_ID, MARKET_MAKER_ACCOUNT_ID
from accounts.models import SystemConfig
from ledger.utils.external_price import USDT, BUY, SELL, fetch_external_price_by_symbol
from ledger.utils.price import USDT_IRT
from market.models import PairSymbol, Order


logger = logging.getLogger(__name__)


@shared_task(queue='celery')
def check_maker_order_price(dry_run=True):
    logger.info('check_maker_order_price')
    if not SystemConfig.get_system_config().market_maker_emergency_brake:
        logger.info('check_maker_order_price canceled due to system config')
        return

    symbols = PairSymbol.objects.filter(enable=True)

    if dry_run:
        symbols = symbols.order_by('?')[:3]
        sides = [BUY if random.randint(0, 1) == 0 else SELL]
    else:
        sides = [BUY, SELL]

    for side in sides:
        usdt_irt_price = fetch_external_price_by_symbol(symbol=USDT_IRT, side=side)

        for symbol in symbols:
            if symbol.name != 'USDTIRT':
                price = fetch_external_price_by_symbol(symbol=symbol.asset.symbol + USDT, side=side)
                price = price if symbol.base_asset.symbol == USDT else (price and usdt_irt_price and price * usdt_irt_price)
            else:
                price = usdt_irt_price

            if price:
                price_q = Q(price__gte=price) if side == BUY else Q(price__lte=price)
                orders = Order.open_objects.filter(
                    price_q,
                    symbol=symbol,
                    side=side,
                    account_id__in=[MARKET_MAKER_ACCOUNT_ID, TRADER_ACCOUNT_ID]
                )
                if orders:
                    if dry_run:
                        logger.warning(f"Trigger Market Maker Emergency Break Due to order:{orders.first().id}")
                        check_maker_order_price(dry_run=False)
                        return
                    else:
                        logger.warning(f'{len(orders)} Order Out of price range Warning, {symbol.name}:{side},'
                                       f' {[i.id for i in orders]}')
                        logger.info(f'{len(orders)} Order Out of price range Warning, {symbol.name}:{side},'
                                    f' {[i.id for i in orders]}')
                        Order.bulk_cancel_simple_orders(orders)
