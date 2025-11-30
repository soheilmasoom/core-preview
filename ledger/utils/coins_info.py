from typing import Dict

from django.core.cache import cache
from django.utils import timezone

from ledger.tasks import populate_coins_info
from ledger.utils.provider import CoinInfo


def get_coins_info() -> Dict[str, CoinInfo]:
    cached_data = cache.get('coins_info') or {}

    if not cached_data or cached_data.get('exp', 0) < timezone.now().timestamp():
        populate_coins_info.delay()

    raw_data = cached_data.get('data', [])

    coins_info = {}

    for info_data in raw_data:
        info = CoinInfo(**info_data)
        coins_info[info.coin] = info

    return coins_info
