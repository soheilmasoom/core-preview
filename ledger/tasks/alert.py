import logging

from celery import shared_task

from accounts.models import Notification
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
    active_alerts = AssetAlertRule.objects.filter(active=True, is_triggered=False)

    for alert in active_alerts:
        if alert.base_asset.symbol == Asset.USDT:
            asset_price = usdt_current_prices.get(alert.asset.symbol)
        else:
            asset_price = irt_current_prices.get(alert.asset.symbol)
        trigger_price = alert.trigger_price

        if not asset_price or not trigger_price:
            continue

        if alert.type == 'gt' and asset_price > trigger_price:
            alert.is_triggered = True
        elif alert.type == 'lt' and asset_price < trigger_price:
            alert.is_triggered = True

        if alert.is_triggered:
            alert.save(update_fields=['is_triggered'])

            Notification.send(
                recipient=alert.user,
                title=f"هشدار قیمت: {alert.asset.symbol}",
                message=f"هشدار قیمت برای ارز {alert.asset.symbol} در قیمت {trigger_price} صادر شد.",
                link=f'/price/{alert.asset.name}'
            )
