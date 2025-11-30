import logging
from dataclasses import dataclass
from decimal import Decimal

from ledger.models import Asset
from ledger.utils.cache import cache_for
from ledger.utils.external_price import BUY, SELL

logger = logging.getLogger(__name__)


@dataclass
class TradingPair:
    side: str
    coin: Asset
    base: Asset
    coin_amount: Decimal
    base_amount: Decimal

    @property
    def symbol(self) -> str:
        return f'{self.coin}{self.base}'


def get_trading_pair(from_asset: Asset, to_asset: Asset, from_amount: Decimal = None, to_amount: Decimal = None) -> TradingPair:

    if from_asset.symbol in (Asset.IRT, Asset.USDT) and to_asset.symbol != Asset.IRT:
        return TradingPair(
            side=BUY,
            coin=to_asset,
            base=from_asset,
            coin_amount=to_amount,
            base_amount=from_amount,
        )

    elif to_asset.symbol in (Asset.IRT, Asset.USDT):
        return TradingPair(
            side=SELL,
            coin=from_asset,
            base=to_asset,
            coin_amount=from_amount,
            base_amount=to_amount,
        )

    else:
        raise NotImplementedError


def get_asset_spread(coin, side: str, value: Decimal = None) -> Decimal:
    from ledger.models import CategorySpread, Asset

    asset = Asset.get(coin)
    step = CategorySpread.get_step(value)

    category = asset.spread_category

    asset_spread = CategorySpread.objects.filter(category=category, step__lte=step, side=side).order_by('-step').first()

    if not asset_spread:
        # logger.warning("No category spread defined for %s step = %s, side = %s" % (category, step, side))
        asset_spread = CategorySpread()

    spread = asset_spread.spread

    if category is None and asset.distribution_factor >= 0.2:
        if side == BUY:
            spread *= Decimal('1.5')

    return spread / 100


def get_market_spread(base_coin: str, side: str, value: Decimal = None) -> Decimal:
    from ledger.models import Asset, MarketSpread, CategorySpread

    step = CategorySpread.get_step(value)

    if base_coin == Asset.IRT:
        market_spread = MarketSpread.objects.filter(step=step, side=side).first()

        if market_spread:
            return market_spread.spread / 100

    return Decimal()


@cache_for(30)
def get_otc_spread(coin: str, side: str, value: Decimal = None, base_coin: str = Asset.USDT) -> Decimal:
    spread = get_asset_spread(coin=coin, side=side, value=value)
    spread += get_market_spread(base_coin=base_coin, side=side, value=value)

    return spread


def spread_to_multiplier(spread: Decimal, side: str):
    if side == BUY:
        return 1 - spread
    else:
        return 1 + spread
