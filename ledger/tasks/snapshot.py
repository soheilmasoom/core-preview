from datetime import datetime

from celery import shared_task
from django.db.models import Q

from ledger.models import SystemSnapshot, Asset, AssetSnapshot
from ledger.utils.overview import AssetOverview
from ledger.utils.price import USDT_IRT


@shared_task(queue='history')
def create_snapshot(now: datetime, prices: dict):
    overview = AssetOverview(prices)

    system_snapshot = SystemSnapshot(
        created=now,
        usdt_price=prices[USDT_IRT],
        hedge=overview.get_total_hedge_value(),
        cum_hedge=overview.get_total_cumulative_hedge_value(),

        total=overview.get_all_real_assets_value(),
        users=overview.get_all_users_asset_value(),
        exchange=overview.get_exchange_assets_usdt(),
        reserved=overview.get_total_reserved_assets_value(),

        margin_insurance=overview.get_margin_insurance_balance(),
        prize=overview.get_all_prize_value(),

        binance_margin_ratio=overview.get_binance_margin_ratio() or 0,
    )

    assets = Asset.live_objects.all()

    for asset in assets.filter(assetsnapshot__isnull=True):
        AssetSnapshot.objects.create(
            asset=asset,
            updated=now,
            price=0,
            hedge_amount=0,
            hedge_value=0,
            hedge_value_abs=0,
            calc_hedge_amount=0,
            total_amount=0,
            users_amount=0,
        )

    for s in AssetSnapshot.objects.filter(Q(asset__enable=True) | ~Q(total_amount=0) | ~Q(users_amount=0)):
        asset = s.asset

        s.updated = now
        s.price = prices.get(asset.symbol + Asset.USDT, 0)
        s.hedge_amount = overview.get_hedge_amount(asset.symbol)
        s.hedge_value = overview.get_hedge_value(asset.symbol)
        s.hedge_value_abs = abs(s.hedge_value)
        s.calc_hedge_amount = 0
        s.total_amount = overview.get_real_assets(asset.symbol)
        s.users_amount = overview.get_users_asset_amount(asset.symbol)

        s.save()

    system_snapshot.save()
