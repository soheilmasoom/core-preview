import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from random import randint
from typing import Set, Dict

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from accounts.models import Notification, User
from accounts.utils.push_notif import send_push_notif
from ledger.models import CoinCategory, AssetAlert, BulkAssetAlert, AlertTrigger, Asset
from ledger.models.asset_alert_rule import AssetAlertRule
from ledger.utils.external_price import BUY
from ledger.utils.precision import get_symbol_presentation_price
from ledger.utils.price import USDT_IRT, get_prices, get_symbol_parts, get_coins_symbols

logger = logging.getLogger(__name__)


CACHE_PREFIX = 'asset_alert'

INTERVAL_HOUR_TIME_MAP = {
    AlertTrigger.ONE_HOUR: 1,
    AlertTrigger.THREE_HOURS: 3,
    AlertTrigger.SIX_HOURS: 6,
    AlertTrigger.TWELVE_HOURS: 12,
    AlertTrigger.ONE_DAY: 24
}

INTERVAL_CHANGE_PERCENT_SENSITIVITY_MAP = {
    AlertTrigger.FIVE_MIN: 5,
    AlertTrigger.ONE_HOUR: 5,
    AlertTrigger.THREE_HOURS: 10,
    AlertTrigger.SIX_HOURS: 10,
    AlertTrigger.TWELVE_HOURS: 20,
    AlertTrigger.ONE_DAY: 20
}


@dataclass
class AlertData:
    user: User
    asset: Asset

    def __hash__(self):
        return hash((self.user, self.asset))

    def __eq__(self, other):
        if not isinstance(other, AlertData):
            return NotImplemented
        return (self.user, self.asset) == (other.user, other.asset)


def get_current_prices(only_base=Asset.USDT) -> dict:
    coins = list(Asset.objects.values_list('symbol', flat=True))
    symbols = get_coins_symbols(coins, only_base=only_base)
    symbols.append(USDT_IRT)

    return get_prices(symbols, side=BUY)


def send_notifications(asset_alerts: Set[AlertData], altered_coins: Dict[str, list]):
    for alert in asset_alerts:
        asset = alert.asset

        is_usdt_based = alert.asset.symbol != Asset.USDT
        base_coin = 'تتر' if is_usdt_based else 'تومان'
        new_price, old_price, interval, is_chanel_changed = altered_coins[alert.asset.symbol]
        percent = math.floor(abs(new_price / old_price - Decimal(1)) * 100)
        change_status = 'افزایش' if new_price > old_price else 'کاهش'
        new_price = get_symbol_presentation_price(
            symbol=alert.asset.symbol + Asset.USDT if is_usdt_based else Asset.IRT,
            amount=new_price,
            trunc_zero=True
        )

        interval_verbose = AlertTrigger.INTERVAL_VERBOSE_MAP[interval]

        if interval == AlertTrigger.FIVE_MIN and not is_chanel_changed:
            title = f'{change_status} ناگهانی قیمت {alert.asset.name_fa}'
        else:
            title = f'{change_status} قیمت {alert.asset.name_fa}'

        if not is_chanel_changed:
            message = (f'قیمت {alert.asset.name_fa} در {interval_verbose} گذشته {percent}'
                       f' درصد {change_status} پیدا کرد و به {new_price} {base_coin} رسید.')
        else:
            message = f'قیمت {alert.asset.name_fa} به {new_price} {base_coin} رسید.'

        send_push_notif(
            title=title,
            body=message,
            link=f'/price/{asset.name}',
            topic=AssetAlert.get_default_rule_push_topic(asset)
        )


def process_chanel_change(asset: Asset, current_chanel: int) -> bool:
    last_chanel_triggered_alerts = AlertTrigger.objects.filter(
        asset=asset,
        is_chanel_changed=True,
        is_triggered=True
    ).order_by('-created')[:2]

    is_chanel_new = not (
            last_chanel_triggered_alerts and
            (last_chanel_triggered_alerts[0].chanel == current_chanel or
             (len(last_chanel_triggered_alerts) == 2 and
              last_chanel_triggered_alerts[1].chanel == current_chanel))
    )

    return is_chanel_new


def process_ratio_change(asset: Asset, interval) -> bool:
    is_sent_recently = AlertTrigger.objects.filter(
        asset=asset,
        created__gte=timezone.now() - timedelta(hours=1),
        is_triggered=True
    ).exists()

    if not is_sent_recently:
        hours = INTERVAL_HOUR_TIME_MAP.get(interval, None)
        is_interval_price_sent_recently = None
        if hours:
            is_interval_price_sent_recently = AlertTrigger.objects.filter(
                asset=asset,
                is_triggered=True,
                interval=interval,
                created__gte=timezone.now() - timedelta(hours=hours)
            ).exists()
        return is_interval_price_sent_recently is False
    else:
        return False


def get_altered_coins(past_cycle_prices: dict, current_cycle: dict, current_cycle_count: int,
                      interval: str) -> Dict[str, list]:
    if not past_cycle_prices:
        return {}

    mapping_symbol = {}

    for asset in Asset.live_objects.exclude(symbol=Asset.IRT):
        coin = asset.symbol
        base_coin = Asset.USDT if coin != Asset.USDT else Asset.IRT
        mapping_symbol[coin + base_coin] = asset

    changed_coins = {}

    for coin in past_cycle_prices.keys() & current_cycle.keys():
        asset = mapping_symbol.get(coin, None)
        if not asset:
            continue

        current_price = current_cycle[coin]
        past_price = past_cycle_prices[coin]
        change_percent = math.floor(Decimal(current_price / past_price - Decimal(1)) * 100)
        is_ratio_changed = abs(change_percent) > INTERVAL_CHANGE_PERCENT_SENSITIVITY_MAP[interval]

        chanel_sensitivity = asset.price_alert_chanel_sensitivity
        current_chanel = current_price // chanel_sensitivity if chanel_sensitivity else None
        past_chanel = past_price // chanel_sensitivity if chanel_sensitivity else None
        is_chanel_changed = abs(current_chanel - past_chanel) >= 1 if (
                chanel_sensitivity and interval == AlertTrigger.FIVE_MIN) else False

        if is_chanel_changed or is_ratio_changed:
            alert_trigger = AlertTrigger.objects.create(
                asset=asset,
                price=current_price,
                cycle=current_cycle_count,
                change_percent=change_percent,
                chanel=current_chanel,
                is_chanel_changed=is_chanel_changed,
                interval=interval
            )

            is_chanel_new = False
            is_ratio_change_alerted = False
            if is_chanel_changed:
                is_chanel_new = process_chanel_change(asset=asset, current_chanel=current_chanel)
            if is_ratio_changed:
                is_ratio_change_alerted = process_ratio_change(asset=asset, interval=interval)

            if is_chanel_new or is_ratio_change_alerted:
                coin, base_coin = get_symbol_parts(coin)
                changed_coins[coin] = [current_price, past_price, interval, is_chanel_new]
                alert_trigger.is_triggered = True
                alert_trigger.save(update_fields=['is_triggered'])

    return changed_coins


def get_past_cycle_by_number(cycle_number: int):
    total_cycles = 24 * 12
    key = CACHE_PREFIX + str(cycle_number % total_cycles)
    return cache.get(key)


def get_asset_alert_list(altered_coins: dict) -> Set[AlertData]:
    asset_alerts = set()
    all_assets = Asset.live_objects.filter(symbol__in=altered_coins.keys())
    all_categories = CoinCategory.objects.all()
    category_map = {}

    for category in all_categories:
        category_map[category] = category.coins.filter(symbol__in=altered_coins.keys())

    for asset_alert in AssetAlert.objects.filter(
        asset__symbol__in=altered_coins.keys(),
        user__is_price_notif_on=True,
    ).exclude(asset__otc_status=Asset.COMING_SOON):
        asset_alerts.add(
            AlertData(
                user=asset_alert.user,
                asset=asset_alert.asset,
            )
        )

    for bulk_asset_alert in BulkAssetAlert.objects.filter(
        user__is_price_notif_on=True
    ):
        subscription_type = bulk_asset_alert.subscription_type

        if subscription_type == BulkAssetAlert.CATEGORY_ALL_COINS:
            subscribed_coins = all_assets
        elif subscription_type == BulkAssetAlert.CATEGORY_MY_ASSETS:
            subscribed_coins = Asset.objects.filter(
                symbol__in=altered_coins.keys(),
                wallet__account=bulk_asset_alert.user.get_account(),
                wallet__balance__gt=0
            )
        else:
            subscribed_coins = category_map[bulk_asset_alert.coin_category]

        for asset in subscribed_coins:
            asset_alerts.add(AlertData(
                user=bulk_asset_alert.user,
                asset=asset
            ))

    return asset_alerts


@shared_task(queue="notif-manager")
def send_price_notifications():
    now = timezone.now()
    current_cycle_count = (now.hour * 60 + now.minute) // 5
    current_cycle_prices = get_current_prices()

    key = CACHE_PREFIX + str(current_cycle_count)
    cache.set(key, current_cycle_prices, 3600 * 24 + 60 * 4)

    past_five_minute_cycle = get_past_cycle_by_number(current_cycle_count - 1)
    past_hour_cycle = get_past_cycle_by_number(current_cycle_count - 12)
    past_three_hours_cycle = get_past_cycle_by_number(current_cycle_count - 12 * 3)
    past_six_hours_cycle = get_past_cycle_by_number(current_cycle_count - 12 * 6)
    past_twelve_hours_cycle = get_past_cycle_by_number(current_cycle_count - 12 * 12)
    past_day_cycle = get_past_cycle_by_number(current_cycle_count + 2)

    altered_coins = {
        **get_altered_coins(past_five_minute_cycle, current_cycle_prices, current_cycle_count,
                            interval=AlertTrigger.FIVE_MIN),
        **get_altered_coins(past_hour_cycle, current_cycle_prices, current_cycle_count,
                            interval=AlertTrigger.ONE_HOUR),
        **get_altered_coins(past_three_hours_cycle, current_cycle_prices, current_cycle_count,
                            interval=AlertTrigger.THREE_HOURS),
        **get_altered_coins(past_six_hours_cycle, current_cycle_prices, current_cycle_count,
                            interval=AlertTrigger.SIX_HOURS),
        **get_altered_coins(past_twelve_hours_cycle, current_cycle_prices, current_cycle_count,
                            interval=AlertTrigger.TWELVE_HOURS),
        **get_altered_coins(past_day_cycle, current_cycle_prices, current_cycle_count,
                            interval=AlertTrigger.ONE_DAY),
    }

    asset_alert_list = get_asset_alert_list(altered_coins)

    send_notifications(asset_alert_list, altered_coins)

    if randint(1, 100) < 10:
        AlertTrigger.objects.filter(created__lte=timezone.now() - timedelta(days=10)).exclude(
            is_chanel_changed=True,
            is_triggered=True
        ).delete()


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
