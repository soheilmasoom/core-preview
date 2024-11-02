import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Union

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from accounts.models import Notification
from accounts.utils.push_notif import send_push_notif
from ledger.models import AlertTrigger, Asset, AssetAlert
from ledger.models.asset_alert_rule import AssetAlertRule
from ledger.utils.external_price import BUY
from ledger.utils.price import USDT_IRT, get_prices, get_symbol_parts, get_coins_symbols

logger = logging.getLogger(__name__)


CACHE_PREFIX = 'asset_alert'

RATIO_INTERVAL_FREEZE_TIME_MAP = {
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


@dataclass()
class AlertData:
    asset: Asset
    cycle: int
    current_price: Decimal
    past_price: Decimal
    interval: str
    trigger_type: str

    @property
    def base_coin(self) -> str:
        if self.asset.symbol == Asset.USDT:
            return Asset.IRT
        else:
            return Asset.USDT


def get_current_prices(only_base=Asset.USDT) -> dict:
    coins = list(Asset.objects.values_list('symbol', flat=True))
    symbols = get_coins_symbols(coins, only_base=only_base)
    symbols.append(USDT_IRT)

    return get_prices(symbols, side=BUY)


def send_notifications(alerts_data: List[AlertData]):
    for alert in alerts_data:
        asset = alert.asset

        base_coin = 'تتر' if alert.base_coin == Asset.USDT else 'تومان'

        percent = math.floor(abs(alert.current_price / alert.past_price - Decimal(1)) * 100)
        change_status = 'افزایش' if alert.current_price > alert.past_price else 'کاهش'

        interval_verbose = AlertTrigger.INTERVAL_VERBOSE_MAP[alert.interval]

        if alert.trigger_type == AlertTrigger.TRIGGER_CHANNEL_CHANGE:
            title = f'{change_status} قیمت {asset.name_fa}'
            message = f'قیمت {asset.name_fa} به {alert.current_price} {base_coin} رسید.'
        else:
            if alert.interval == AlertTrigger.FIVE_MIN:
                title = f'{change_status} ناگهانی قیمت {asset.name_fa}'
            else:
                title = f'{change_status} قیمت {asset.name_fa}'

            message = (f'قیمت {asset.name_fa} در {interval_verbose} گذشته {percent}'
                       f' درصد {change_status} پیدا کرد و به {alert.current_price} {base_coin} رسید.')

        AlertTrigger.objects.create(
            asset=asset,
            trigger_type=alert.trigger_type,
            cycle=alert.cycle,
            old_price=alert.past_price,
            new_price=alert.current_price,
            interval=alert.interval,
        )

        send_push_notif(
            title=title,
            body=message,
            link=f'/price/{asset.name}',
            topic=AssetAlert.get_default_rule_push_topic(asset),
            ttl=3600
        )


def get_crossing_channel(old_channel: int, new_channel: int) -> Union[int, None]:
    # if channel changed from 59 to 60 => crossing channel is 60
    # if channel changed from 60 to 59 => crossing channel is 60 also
    # if channel changed from 60 to 62 => crossing channel is 62
    # if channel changed from 62 to 60 => crossing channel is 61

    channel_change = new_channel - old_channel

    if channel_change >= 1:
        return new_channel
    elif channel_change <= -1:
        return new_channel + 1


def get_channel_change_trigger_data(asset: Asset, old_price: Decimal, new_price: Decimal) -> bool:

    if not asset.price_alert_channel_sensitivity:
        return False

    channel_sensitivity = asset.price_alert_channel_sensitivity

    new_channel = new_price // channel_sensitivity
    old_channel = old_price // channel_sensitivity

    crossing_channel = get_crossing_channel(old_channel=old_channel, new_channel=new_channel)

    if not crossing_channel:
        return False

    last_alert_trigger = AlertTrigger.objects.filter(
        asset=asset,
        trigger_type=AlertTrigger.TRIGGER_CHANNEL_CHANGE,
    ).order_by('created').last()

    if not last_alert_trigger:
        return True

    last_old_channel = last_alert_trigger.old_price // channel_sensitivity
    last_new_channel = last_alert_trigger.new_price // channel_sensitivity

    last_crossing_channel = get_crossing_channel(old_channel=last_old_channel, new_channel=last_new_channel)

    if not last_crossing_channel or last_crossing_channel != crossing_channel:
        return True


def should_trigger_ratio_change(asset: Asset, interval) -> bool:
    # Do not send two alerts for any asset in one hour!
    recently_sent = AlertTrigger.objects.filter(
        asset=asset,
        created__gte=timezone.now() - timedelta(hours=1),
    ).exists()

    if recently_sent:
        return False

    # Do not send two alerts for any asset in its interval
    freeze_time = RATIO_INTERVAL_FREEZE_TIME_MAP.get(interval)

    if not freeze_time:
        return True

    recently_interval_sent = AlertTrigger.objects.filter(
        asset=asset,
        interval=interval,
        created__gte=timezone.now() - timedelta(hours=freeze_time)
    ).exists()

    return not recently_interval_sent


def get_ratio_alerts(current_cycle_prices: dict, current_cycle: int, symbol_to_asset_mapping: dict, interval: str) \
        -> Dict[str, AlertData]:

    interval_cycles_count = AlertTrigger.INTERVAL_MINUTES_MAPPING[interval] // 5  # every cycle has 5 minutes length
    if interval == AlertTrigger.ONE_DAY:
        interval_cycles_count -= 2  # Because we have only 1 day of cycles!

    past_cycle_prices = get_past_cycle_by_number(current_cycle - interval_cycles_count)

    if not past_cycle_prices:
        return {}

    alerts = {}

    for symbol in past_cycle_prices.keys() & current_cycle_prices.keys():
        asset = symbol_to_asset_mapping.get(symbol)
        if not asset:
            continue

        current_price = current_cycle_prices[symbol]
        past_price = past_cycle_prices[symbol]
        coin, base_coin = get_symbol_parts(symbol)

        ratio = math.floor(Decimal(current_price / past_price - Decimal(1)) * 100)
        is_ratio_changed = abs(ratio) > INTERVAL_CHANGE_PERCENT_SENSITIVITY_MAP[interval]

        if is_ratio_changed and should_trigger_ratio_change(asset, interval):
            alerts[coin] = AlertData(
                asset=asset,
                cycle=current_cycle,
                current_price=current_price,
                past_price=past_price,
                interval=interval,
                trigger_type=AlertTrigger.TRIGGER_PRICE_RATIO
            )

    return alerts


def get_channel_change_alerts(current_cycle_prices: dict, current_cycle: int, symbol_to_asset_mapping: dict):
    past_cycle_prices = get_past_cycle_by_number(current_cycle - 1)  # 5 minutes ago

    if not past_cycle_prices:
        return {}

    alerts = {}

    for symbol in past_cycle_prices.keys() & current_cycle_prices.keys():
        asset = symbol_to_asset_mapping.get(symbol)
        if not asset:
            continue

        current_price = current_cycle_prices[symbol]
        past_price = past_cycle_prices[symbol]
        coin, base_coin = get_symbol_parts(symbol)

        channel_change_data = get_channel_change_trigger_data(asset, old_price=past_price, new_price=current_price)

        if channel_change_data:
            alerts[coin] = AlertData(
                asset=asset,
                cycle=current_cycle,
                current_price=current_price,
                past_price=past_price,
                interval=AlertTrigger.FIVE_MIN,
                trigger_type=AlertTrigger.TRIGGER_CHANNEL_CHANGE,
            )

    return alerts


def get_past_cycle_by_number(cycle_number: int):
    total_cycles = 24 * 12
    key = CACHE_PREFIX + str(cycle_number % total_cycles)
    return cache.get(key)


@shared_task(queue="notif-manager")
def send_price_notifications():
    now = timezone.now()
    current_cycle = (now.hour * 60 + now.minute) // 5
    current_cycle_prices = get_current_prices()

    if not current_cycle_prices:
        return

    key = CACHE_PREFIX + str(current_cycle)
    cache.set(key, current_cycle_prices, 3600 * 24 + 60 * 4)

    # past_day_cycle_prices = get_past_cycle_by_number(current_cycle + 2)

    symbol_to_asset = {}

    for asset in Asset.live_objects.exclude(symbol=Asset.IRT):
        coin = asset.symbol
        base_coin = Asset.USDT if coin != Asset.USDT else Asset.IRT
        symbol_to_asset[coin + base_coin] = asset

    altered_coins = {
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.ONE_DAY),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.TWELVE_HOURS),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.SIX_HOURS),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.THREE_HOURS),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.ONE_HOUR),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.FIVE_MIN),
    }

    send_notifications(list(altered_coins.values()))

    # if randint(1, 100) < 10:
    #     AlertTrigger.objects.filter(created__lte=timezone.now() - timedelta(days=10)).exclude(
    #         is_chanel_changed=True,
    #         is_triggered=True
    #     ).delete()


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
