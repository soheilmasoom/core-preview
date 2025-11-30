from json import JSONDecodeError

import requests
from django.core.cache import cache
from urllib3.exceptions import ReadTimeoutError

from accounts.verifiers.jibit import Response
from ledger.utils.cache import get_cache_func_key


class BaseRequester:
    CACHE_PREFIX = None
    BASE_TIMEOUT = 10

    def get_auth_token(self):
        raise NotImplementedError

    def get_base_url(self):
        raise NotImplementedError

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, cache_timeout: int = None,
                    timeout: float = BASE_TIMEOUT) -> Response:
        cache_key = None
        caching_allowed = self.CACHE_PREFIX and cache_timeout

        if caching_allowed:
            cache_key = f'{self.CACHE_PREFIX}:{get_cache_func_key(self.__class__, path, method, data)}'
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return Response(data=cached_result)

        result = self._collect_api(path, method, data, timeout=timeout)

        if caching_allowed and result.success:
            cache.set(cache_key, result.data, cache_timeout)

        return result

    def _collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 10) -> Response:
        if data is None:
            data = {}

        url = self.get_base_url() + path
        token = self.get_auth_token()

        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': token},
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
