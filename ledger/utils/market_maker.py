import logging
from json import JSONDecodeError

import requests
from decouple import config
from django.conf import settings
from django.core.cache import cache
from urllib3.exceptions import ReadTimeoutError

from accounts.verifiers.jibit import Response
from ledger.utils.cache import get_cache_func_key

logger = logging.getLogger(__name__)


class MarketMakerRequester:
    def collect_api(self, path: str, method: str = 'GET', data: dict = None, cache_timeout: int = None) -> Response:
        cache_key = None
        if cache_timeout:
            cache_key = 'market_maker:' + get_cache_func_key(self.__class__, path, method, data)
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return Response(data=cached_result)

        result = self._collect_api(path, method, data)

        if cache_timeout and result.success:
            cache.set(cache_key, result.data, cache_timeout)

        return result

    def _collect_api(self, path: str, method: str = 'GET', data: dict = None) -> Response:
        if data is None:
            data = {}

        url = config('MARKET_MAKER_BASE_URL', default='https://maker.raastin.com') + path

        request_kwargs = {
            'url': url,
            'timeout': 60,
            'headers': {'Authorization': config('MARKET_MAKER_TOKEN')},
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)
        except (requests.exceptions.ConnectionError, ReadTimeoutError, requests.exceptions.Timeout):
            raise TimeoutError

        try:
            resp_json = resp.json()
        except JSONDecodeError:
            resp_json = None

        return Response(data=resp_json, success=resp.ok, status_code=resp.status_code)

    def get_trade_hedge_info(self, origin_id: str) -> dict:
        resp = self.collect_api(f'/api/v1/trades/{origin_id}/')

        if resp.status_code == 404:
            logger.warning(f'MarketMaker Missing Order:{origin_id}')
            # send_system_message(
            #     f'Market maker missing order:{origin_id}',
            #     link=url_to_admin_list(Trade, filters={'id': origin_id})
            # )

        return resp.data


class MockMarketMakerRequester(MarketMakerRequester):
    def get_trade_hedge_info(self, origin_id: str) -> dict:
        return {"origin_id": 26059774, "real_revenue": "0.05919748", "hedge_price": "50000","amount":"8.72000000"}


def get_market_maker_requester() -> MarketMakerRequester:
    if settings.DEBUG_OR_TESTING:
        return MockMarketMakerRequester()
    else:
        return MarketMakerRequester()
