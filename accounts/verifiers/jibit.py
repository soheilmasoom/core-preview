import datetime
import logging

import requests
from decouple import config
from django.core.cache import caches
from django.utils import timezone
from urllib3.exceptions import ReadTimeoutError

from accounts.models import UserAuthRequest
from accounts.utils.validation import gregorian_to_jalali_date_str
from accounts.verifiers.utils import *


logger = logging.getLogger(__name__)
token_cache = caches['token']

JIBIT_TOKEN_KEY = 'jibit-token'


class JibitRequester:
    BASE_URL = 'https://napi.jibit.ir/ide'

    RESULT_MAP = {
        'mobileNumber.not_valid': 'INVALID_DATA',
        'nationalCode.not_valid': 'INVALID_DATA',
        'card.provider_is_not_active': 'PROVIDER_IS_NOT_ACTIVE',
        'card.source_bank_is_not_active': 'PROVIDER_IS_NOT_ACTIVE',
        'iban.not_valid': 'INVALID_IBAN',
        'identity_info.not_found': 'INVALID_DATA',
        'matching.unknown': 'INVALID_DATA'
    }

    def __init__(self, user):
        self._user = user

    def _get_cc_token(self, force_renew: bool = False):
        if not force_renew:
            token = token_cache.get(JIBIT_TOKEN_KEY)
            if token:
                return token

        resp = requests.post(
            url=self.BASE_URL + '/v1/tokens/generate',
            json={
                'apiKey': config('JIBIT_API_KEY'),
                'secretKey': config('JIBIT_API_SECRET'),
            },
            timeout=30,
            # proxies={
            #     'https': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            #     'http': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            #     'ftp': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            # }
        )

        if resp.ok:
            resp_data = resp.json()
            token = resp_data['accessToken']
            expire = 24 * 3600

            token_cache.set(JIBIT_TOKEN_KEY, token, expire)

            return token

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, force_renew_token: bool = False,
                    search_key: str = '', weight: int = 0) -> Response:

        if search_key:
            request = UserAuthRequest.objects.filter(
                created__gt=timezone.now() - datetime.timedelta(days=30),
                search_key=search_key,
                service=UserAuthRequest.JIBIT,
            ).order_by('-created').first()

            if request:

                if request.status_code >= 500:
                    raise ServerError('Jibit verifier request error')

                return Response(data=request.response, success=request.status_code in (200, 201))

        token = self._get_cc_token()

        if data is None:
            data = {}

        url = self.BASE_URL + path

        req_object = UserAuthRequest.objects.create(
            url=url,
            method=method,
            data=data,
            user=self._user,
            service=UserAuthRequest.JIBIT,
            weight=weight,
        )

        request_kwargs = {
            'url': url,
            'timeout': 30,
            'headers': {'Authorization': 'Bearer ' + token},
            # 'proxies': {
            #     'https': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            #     'http': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            #     'ftp': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            # }
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)
        except (requests.exceptions.ConnectionError, ReadTimeoutError, requests.exceptions.Timeout):
            req_object.response = 'timeout'
            req_object.status_code = 100
            req_object.save()

            logger.error('jibit connection error', extra={
                'path': path,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        if not force_renew_token and resp.status_code == 403:
            return self.collect_api(path, method, data, force_renew_token=True, search_key=search_key, weight=weight)

        resp_data = resp.json()

        req_object.response = resp_data
        req_object.status_code = resp.status_code

        if search_key and resp.status_code not in (403, 401) and resp.status_code < 500 and \
                resp_data.get('code') not in ['card.provider_is_not_active', 'card.source_bank_is_not_active']:

            req_object.search_key = search_key

        req_object.save()

        if resp.status_code >= 500:
            logger.error('failed to call jibit', extra={
                'path': path,
                'method': method,
                'data': data,
                'resp': resp_data,
                'status': resp.status_code
            })
            print(resp_data)

            raise ServerError('Jibit verifier request error')

        return Response(data=resp_data, success=resp.ok)

    def matching(self, phone_number: str = None, national_code: str = None, full_name: str = None,
                 birth_date: datetime = None, card_pan: str = None, iban: str = None) -> Response:

        if birth_date:
            birth_date = gregorian_to_jalali_date_str(birth_date).replace('/', '')

        params = {
            'mobileNumber': phone_number,
            'nationalCode': national_code,
            'birthDate': birth_date,
            'name': full_name,
            'cardNumber': card_pan,
            'iban': iban,
        }

        key = 'matching-' + '-'.join(map(lambda s: s or '', params.values()))

        params = {k: v for (k, v) in params.items() if v}

        resp = self.collect_api(
            path='/v1/services/matching',
            data=params,
            search_key=key,
            weight=UserAuthRequest.JIBIT_ADVANCED_MATCHING if national_code else UserAuthRequest.JIBIT_SIMPLE_MATCHING
        )
        data = resp.data
        resp.data = MatchingData(
            is_matched=data.get('matched', False),
            code=JibitRequester.RESULT_MAP.get(
                data.get('code', ''),
                'INVALID_DATA' if data.get('code', '').startswith('card.') else data.get('code', '')
            )
        )
        return resp

    def get_iban_info(self, iban: str) -> Response:
        params = {
            'value': iban,
        }

        key = 'iban-%s' % iban

        resp = self.collect_api(
            path='/v1/ibans',
            data=params,
            search_key=key,
            weight=UserAuthRequest.JIBIT_IBAN_INFO_WEIGHT,
        )
        data = resp.data
        info = data.get('ibanInfo', {})
        resp.data = IBANInfoData(
            bank_name=info.get('bank', ''),
            deposit_number=info.get('depositNumber', ''),
            deposit_status=info.get('status', ''),
            owners=info.get('owners', []),
            code=data.get('code', '')
        )
        return resp

    def get_card_info(self, card_pan: str) -> Response:
        params = {
            'number': card_pan,
        }

        key = 'card-%s' % card_pan

        resp = self.collect_api(
            path='/v1/cards',
            data=params,
            search_key=key,
            weight=UserAuthRequest.JIBIT_CARD_INFO_WEIGHT
        )
        data = resp.data
        info = data.get('cardInfo', {})
        resp.data = CardInfoData(
            owner_name=info.get('ownerName', ''),
            bank_name=info.get('bank', ''),
            card_type=info.get('type', ''),
            deposit_number=info.get('depositNumber', ''),
            code=JibitRequester.RESULT_MAP.get(
                data.get('code', ''),
                'INVALID_DATA' if data.get('code', '').startswith('card.') else data.get('code', '')
            )
        )
        return resp
