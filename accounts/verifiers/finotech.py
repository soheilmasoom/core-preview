import datetime
import logging

import requests
from django.core.cache import caches
from django.utils import timezone
from urllib3.exceptions import ReadTimeoutError
from decouple import config
from decouple import config

from accounts.models import FinotechRequest
from accounts.utils.validation import gregorian_to_jalali_date_str

logger = logging.getLogger(__name__)

token_cache = caches['token']


FINOTECH_TOKEN_KEY = 'finotech-token'


class FinotechRequester:
    def __init__(self, user):
        self._user = user

    def _get_cc_token(self, force_renew: bool = False):

        if not force_renew:
            token = token_cache.get(FINOTECH_TOKEN_KEY)
            if token:
                return token

        scopes = ['facility:shahkar:get', 'facility:cc-nid-verification:get', 'kyc:mobile-card-verification:post',
                  'oak:iban-inquiry:get']

        resp = requests.post(
            url='https://apibeta.finnotech.ir/dev/v2/oauth2/token',
            data={
                'grant_type': 'client_credentials',
                'nid': config('FINOTECH_OWNER_NATIONAL_ID'),
                'scopes': ','.join(scopes)
            },
            headers={
                'Authorization': config('FINOTECH_AUTH_TOKEN')
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()['result']
            token = resp_data['value']
            expire = resp_data['lifeTime'] // 1000

            token_cache.set(FINOTECH_TOKEN_KEY, token, expire)

            return token

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, force_renew_token: bool = False,
                    search_key: str = None) -> dict:

        if search_key:
            request = FinotechRequest.objects.filter(
                created__gt=timezone.now() - datetime.timedelta(days=30),
                search_key=search_key,
                service=FinotechRequest.FINOTECH
            ).order_by('-created').first()

            if request:

                if request.status_code >= 500:
                    raise ServerError('Finotech requester error')

                if request.status_code not in (200, 201):
                    return

                return request.response['result']

        token = self._get_cc_token()

        if data is None:
            data = {}

        url = 'https://apibeta.finnotech.ir' + path.format(clientId='raastin')

        req_object = FinotechRequest.objects.create(
            url=url,
            method=method,
            data=data,
            user=self._user,
            service=FinotechRequest.FINOTECH
        )

        url += '?trackId=%s' % req_object.track_id

        request_kwargs = {
            'url': url,
            'timeout': 10,
            'headers': {'Authorization': 'Bearer ' + token},
            'proxies': {
                'https': config('IRAN_PROXY_IP', default='localhost') + ':3128',
                'http': config('IRAN_PROXY_IP', default='localhost') + ':3128',
                'ftp': config('IRAN_PROXY_IP', default='localhost') + ':3128',
            }
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(data=data, **request_kwargs)
        except (requests.exceptions.ConnectionError, ReadTimeoutError, requests.exceptions.Timeout):
            req_object.response = 'timeout'
            req_object.status_code = 100
            req_object.save()

            logger.error('finnotech connection error', extra={
                'path': path,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        if not force_renew_token and resp.status_code == 403:
            return self.collect_api(path, method, data, force_renew_token=True, search_key=search_key)

        resp_data = resp.json()

        req_object.response = resp_data
        req_object.status_code = resp.status_code

        if resp.ok or (resp.status_code == 400 and 'nidVerification' in path):
            req_object.search_key = search_key

        req_object.save()

        if resp.status_code >= 500:
            raise ServerError('Finotech requester error')

        if not resp.ok:
            logger.error('failed to call finnotech', extra={
                'path': path,
                'method': method,
                'data': data,
                'resp': resp_data,
                'status': resp.status_code
            })
            print(resp_data)
            return

        return resp_data['result']

    def verify_phone_number_national_code(self, phone_number: str, national_code: str) -> bool:
        resp = self.collect_api(
            path='/facility/v2/clients/{clientId}/shahkar/verify',
            data={
                'mobile': phone_number,
                'nationalCode': national_code
            },
            search_key='shahkar-%s-%s' % (national_code, phone_number)
        )

        if not resp:
            raise ServerError('Finotech requester error')

        return resp['isValid']

    def get_iban_info(self, iban: str) -> dict:
        resp = self.collect_api(
            path='/oak/v2/clients/{clientId}/ibanInquiry',
            data={
                'iban': iban,
            },
            search_key='iban-%s' % iban
        )

        return resp

    def verify_card_pan_phone_number(self, phone_number: str, card_pan: str) -> bool:
        resp = self.collect_api(
            path='/kyc/v2/clients/{clientId}/mobileCardVerification',
            method='POST',
            data={
                'mobile': phone_number,
                'card': card_pan
            },
            search_key='mobcard-%s-%s' % (phone_number, card_pan)
        )

        if not resp:
            raise ServerError('Finotech requester error')

        return resp['isValid']

    def verify_basic_info(self, national_code: str, birth_date: datetime.date, first_name: str, last_name: str, ) -> dict:
        jalali_date = gregorian_to_jalali_date_str(birth_date)

        resp = self.collect_api(
            path='/facility/v2/clients/{clientId}/users/%s/cc/nidVerification' % national_code,
            data={
                'birthDate': jalali_date,
                'firstName': first_name,
                'lastName': last_name,
            },
            search_key='nid-%s-%s-%s-%s' % (national_code, jalali_date, first_name, last_name)
        )

        return resp
