import math
from decimal import Decimal

from ledger.models import Asset
from ledger.utils.price import get_last_price
from market.consts import OTC_MIN_HARD_FIAT_VALUE
from market.models import PairSymbol


def create_symbols_for_asset(asset: Asset):
    if asset.symbol == Asset.IRT:
        return

    irt_asset = Asset.objects.get(symbol=Asset.IRT)
    usdt_asset = Asset.objects.get(symbol=Asset.USDT)

    base_assets = [irt_asset, usdt_asset]

    if asset.symbol == Asset.USDT:
        base_assets = [irt_asset]

    price_irt = get_last_price(asset.symbol + Asset.IRT)

    step_size = min(max(math.ceil(math.log10(price_irt / OTC_MIN_HARD_FIAT_VALUE)), 0), 8)

    for base_asset in base_assets:
        price = get_last_price(asset.symbol + base_asset.symbol)

        tick_size = min(max(math.ceil(-math.log10(price)) + 3, 0), 8)

        PairSymbol.objects.update_or_create(
            asset=asset, base_asset=base_asset, defaults={
                'name': f'{asset.symbol}{base_asset.symbol}',
                'tick_size': tick_size,
                'step_size': step_size,
                'min_trade_quantity': Decimal('0.0001') / price,
                'max_trade_quantity': Decimal(1000_000) / price,
            }
        )


def check_pair_symbol(p, up: bool = False):
    asset = p.asset
    price_irt = get_last_price(asset.symbol + Asset.IRT)

    if not price_irt:
        print('ignore %s due to null price' % p)
        return
    step_size = math.ceil(math.log10(price_irt / OTC_MIN_HARD_FIAT_VALUE))
    if step_size > p.step_size:
        print(p, step_size, p.step_size, step_size > p.step_size)
        if up:
            p.step_size = step_size
            p.save(update_fields=['step_size'])
