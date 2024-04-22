import logging
from collections import defaultdict
from decimal import Decimal

import requests
from django.conf import settings

from accounting.models.periodic_fetcher import FetchError
from ledger.utils.cache import cache_for

logger = logging.getLogger(__name__)


class InternalAssetsRequester:
    def __init__(self):
        self.header = {
            'Authorization': settings.BLOCKLINK_TOKEN
        }

    def get_assets(self, with_network: bool = False) -> list:
        if settings.DEBUG_OR_TESTING_OR_STAGING:
            return []

        params = None

        if with_network:
            params = {'network': 1}

        resp = requests.get(
            url=settings.BLOCKLINK_BASE_URL + '/api/v1/hotwallet/amount/',
            headers=self.header,
            params=params,
            timeout=30
        )

        if not resp.ok:
            raise FetchError

        return resp.json()

    def get_hot_wallets(self) -> list:
        if settings.DEBUG_OR_TESTING_OR_STAGING:
            return []

        resp = requests.get(
            url=settings.BLOCKLINK_BASE_URL + '/api/v1/hotwallet/balances/',
            headers=self.header,
            timeout=30
        )

        if not resp.ok:
            raise FetchError

        return resp.json()


@cache_for(60)
def get_internal_asset_deposits() -> dict:
    assets = InternalAssetsRequester().get_assets(with_network=True)

    if not assets:
        return {}

    result = defaultdict(dict)

    for asset in assets:
        result[asset['network']][asset['coin']] = Decimal(asset['amount'])

    return result


@cache_for(60)
def get_hot_wallet_balances() -> dict:
    hot_wallets = InternalAssetsRequester().get_hot_wallets()

    return {
        (hw['coin'], hw['network']): Decimal(hw['balance']) for hw in hot_wallets
    }
