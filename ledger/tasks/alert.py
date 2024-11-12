import logging

from celery import shared_task

from ledger.models import Asset
from ledger.models.asset_alert_rule import AssetAlertRule
from ledger.utils.auto_price_alert import process_automated_price_alerts, get_current_prices

logger = logging.getLogger(__name__)


@shared_task(queue="notif-manager")
def send_price_notifications():
    process_automated_price_alerts()


@shared_task(queue="notif-manager")
def check_conditional_price_alerts():
    usdt_current_prices = get_current_prices(only_base=Asset.USDT)
    irt_current_prices = get_current_prices(only_base=Asset.IRT)

    to_trigger_alert_rules = AssetAlertRule.objects.filter(
        active=True,
        asset_alert__active=True,
    ).prefetch_related('asset_alert__asset', 'asset_alert__user')

    for alert_rule in to_trigger_alert_rules:
        asset = alert_rule.asset_alert.asset
        if alert_rule.base_asset.symbol == Asset.USDT:
            current_price = usdt_current_prices.get(asset.symbol)
        else:
            current_price = irt_current_prices.get(asset.symbol)

        if not current_price:
            continue

        alert_rule.update_current_price(current_price)
