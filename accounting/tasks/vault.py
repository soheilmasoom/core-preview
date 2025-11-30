from celery.app import shared_task
from django.utils import timezone

from accounting.utils.vault import update_provider_vaults, update_hot_wallet_vault, update_gateway_vaults, \
    update_asset_prices, update_cold_wallet_vaults, update_reserved_assets_value, update_bank_vaults, \
    update_service_vaults
from ledger.models import Asset
from ledger.tasks import create_snapshot
from ledger.utils.price import get_coins_symbols, get_last_prices


@shared_task(queue='vault')
def update_vaults():
    coins = Asset.live_objects.all().values_list('symbol', flat=True)
    prices = get_last_prices(get_coins_symbols(coins))
    now = timezone.now().replace(second=0, microsecond=0)

    update_provider_vaults(now, prices)
    update_hot_wallet_vault(now, prices)
    update_gateway_vaults(now, prices)
    update_bank_vaults(now, prices)
    update_cold_wallet_vaults(now, prices)
    update_service_vaults(now, prices)

    update_reserved_assets_value(now, prices)
    update_asset_prices(now, prices)
    create_snapshot(now, prices)
