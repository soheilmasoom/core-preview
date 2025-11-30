from collections import defaultdict

from celery import shared_task
from django.db.models import Sum

from accounts.models import Account
from ledger.models import Wallet, Asset
from ledger.utils.price import get_last_prices, get_coins_symbols


def get_distribution_factor(nums: list) -> float:
    if not nums:
        return 1.0

    squad_sum = sum([x * x for x in nums])
    normal_sum = sum(nums)

    return squad_sum / normal_sum / normal_sum


@shared_task
def update_distribution_factors():
    wallets = Wallet.objects.filter(
        account__type=Account.ORDINARY
    ).filter(
        asset__enable=True
    ).exclude(
        asset__symbol__in=(Asset.IRT, Asset.USDT)
    ).exclude(
        market=Wallet.VOUCHER
    ).values('account', 'asset').annotate(
        sum=Sum('balance')
    ).filter(sum__gt=0)

    per_asset_distribution = defaultdict(list)

    for w in wallets:
        per_asset_distribution[w['asset']].append(w['sum'])

    assets = Asset.live_objects.all()

    prices = get_last_prices(get_coins_symbols(list(assets.values_list('symbol', flat=True)), only_base=Asset.USDT))

    assets_list = list(assets)

    for asset in assets_list:
        total = sum(per_asset_distribution[asset.id])
        price = prices.get(asset.symbol)

        if price is None:
            continue

        if total * price < 100:
            asset.distribution_factor = 0
        else:
            asset.distribution_factor = get_distribution_factor(per_asset_distribution[asset.id])

    Asset.objects.bulk_update(assets_list, fields=['distribution_factor'])
