from decimal import Decimal

from ledger.models import Asset
from ledger.utils.precision import floor_precision
from ledger.utils.price import get_last_price
from market.models import PairSymbol


def reset_maker_amounts(value: int = 1000):
    for symbol in PairSymbol.objects.filter(asset__enable=True):
        price = get_last_price(symbol.asset.symbol + Asset.USDT)

        symbol.maker_amount = floor_precision(
            (Decimal(value) / price), symbol.step_size)
        symbol.save()
