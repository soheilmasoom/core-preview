import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Union

from django.core.cache import cache
from django.utils import timezone

from accounts.utils.push_notif import send_push_notif
from ledger.models import AlertTrigger, Asset, AssetAlert
from ledger.utils.precision import get_presentation_amount
from ledger.utils.price import USDT_IRT, get_symbol_parts, get_coins_symbols, get_last_prices

logger = logging.getLogger(__name__)


CACHE_PREFIX = 'asset_alert'

INTERVAL_CHANGE_PERCENT_SENSITIVITY_MAP = {
    AlertTrigger.FIVE_MIN: 5,
    AlertTrigger.ONE_HOUR: 5,
    AlertTrigger.THREE_HOURS: 10,
    AlertTrigger.SIX_HOURS: 10,
    AlertTrigger.TWELVE_HOURS: 10,
    AlertTrigger.ONE_DAY: 10
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

    return get_last_prices(symbols)


def send_notifications(alerts_data: List[AlertData]):
    for alert in alerts_data:
        asset = alert.asset

        base_coin = 'تتر' if alert.base_coin == Asset.USDT else 'تومان'

        percent = math.floor(abs(alert.current_price / alert.past_price - Decimal(1)) * 100)
        change_status = 'افزایش' if alert.current_price > alert.past_price else 'کاهش'

        interval_verbose = AlertTrigger.INTERVAL_VERBOSE_MAP[alert.interval]

        current_price_presentation = get_presentation_amount(alert.current_price)

        coin_name = asset.original_name_fa or asset.name_fa
        title = coin_name

        if alert.trigger_type == AlertTrigger.TRIGGER_CHANNEL_CHANGE:
            message = f'{change_status} قیمت {asset.name_fa} به {current_price_presentation} {base_coin}'
        else:
            message = f'{change_status} {percent} درصدی {coin_name} در {interval_verbose} گذشته'

        fcm_key = send_push_notif(
            title=title,
            body=message,
            link=f'/price/{asset.name}',
            topic=AssetAlert.get_default_rule_push_topic(asset),
            ttl=3600
        )

        AlertTrigger.objects.create(
            asset=asset,
            trigger_type=alert.trigger_type,
            cycle=alert.cycle,
            old_price=alert.past_price,
            new_price=alert.current_price,
            interval=alert.interval,
            fcm_key=fcm_key or ''
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
    # Do not send two alerts for any asset in its interval
    freeze_time = max(AlertTrigger.INTERVAL_MINUTES_MAPPING.get(interval, 0), 60)

    recently_interval_sent = AlertTrigger.objects.filter(
        asset=asset,
        created__gte=timezone.now() - timedelta(minutes=freeze_time)
    ).exists()

    return not recently_interval_sent


def get_ratio_alerts(current_cycle_prices: dict, current_cycle: int, symbol_to_asset_mapping: dict, interval: str) \
        -> Dict[str, AlertData]:

    cycle_diff = AlertTrigger.INTERVAL_MINUTES_MAPPING[interval] // 5  # every cycle has 5 minutes length
    if interval == AlertTrigger.ONE_DAY:
        cycle_diff -= 2  # Because we have only 1 day of cycles!

    past_cycle_prices = get_cycle_prices(current_cycle - cycle_diff, diff=cycle_diff)

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

        sensitivity = INTERVAL_CHANGE_PERCENT_SENSITIVITY_MAP[interval]
        category = asset.spread_category
        if category and category.name == 'high-risk':
            sensitivity *= 2

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
    past_cycle_prices = get_cycle_prices(current_cycle - 1, diff=1)  # 5 minutes ago

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


def get_cycle_prices(cycle: int, diff: int):
    total_cycles = 24 * 12
    key = CACHE_PREFIX + str(cycle % total_cycles)

    if diff == 1 and cache.ttl(key) < 20 * 3600:  # todo: remove me (this is code is needed only 24h after commit!)
        return

    return cache.get(key)


def process_automated_price_alerts():
    now = timezone.now()
    current_cycle = (now.hour * 60 + now.minute) // 5
    current_cycle_prices = get_current_prices()

    if not current_cycle_prices:
        return

    key = CACHE_PREFIX + str(current_cycle)
    cache.set(key, current_cycle_prices, 3600 * 24)

    # past_day_cycle_prices = get_past_cycle_by_number(current_cycle + 2)

    symbol_to_asset = {}

    for asset in Asset.live_objects.exclude(symbol=Asset.IRT):
        coin = asset.symbol
        base_coin = Asset.USDT if coin != Asset.USDT else Asset.IRT
        symbol_to_asset[coin + base_coin] = asset

    # lowest has most priority
    altered_coins = {
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.FIVE_MIN),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.ONE_HOUR),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.THREE_HOURS),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.SIX_HOURS),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.TWELVE_HOURS),
        **get_ratio_alerts(current_cycle_prices, current_cycle, symbol_to_asset, interval=AlertTrigger.ONE_DAY),
        **get_channel_change_alerts(current_cycle_prices, current_cycle, symbol_to_asset),
    }

    send_notifications(list(altered_coins.values()))
