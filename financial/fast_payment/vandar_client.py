import logging
from json import JSONDecodeError

import requests
from django.conf import settings
from urllib3.exceptions import ReadTimeoutError

from accounts.models import User
from accounts.verifiers.jibit import Response
from financial.fast_payment.base_client import BaseClient
from financial.models.authorization_id import AuthorizationId
from financial.models.fast_payment_bank import FastPaymentBank

logger = logging.getLogger(__name__)


class VandarClient(BaseClient):
    BASE_URL = 'https://api.vandar.io'
    _token = None

    def get_token(self, force_renew: bool = False):
        if not force_renew:
            if self._token:
                return self._token

        resp = requests.post(
            url=self.BASE_URL + '/v3/refreshtoken',
            headers={
                'Content-Type': 'application/json'
            },
            json={
                'refreshtoken': f'{self.gateway.refresh_token}',
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            print(resp_data['refresh_token'])
            self.gateway.set_refresh_token(resp_data['refresh_token'])
            self._token = resp_data['access_token']
            return self._token

    def _collect_api(self, path: str, method: str = 'GET', headers: dict = None, data: dict = None) -> Response:
        if data is None:
            data = {}

        url = self.BASE_URL + path

        token = self.get_token()

        if not token:
            return Response(None, False, status_code=0)

        headers = headers or {}

        request_kwargs = {
            'url': url,
            'timeout': 30,
            'headers': {
                'Authorization': 'Bearer ' + token,
                **headers
            }
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

        if not resp.ok:
            logger.info(f'{url} {resp.status_code}: {resp_json}')

        return Response(data=resp_json, success=resp.ok, status_code=resp.status_code)

    def update_banks(self):
        banks = self.get_banks()

        if not banks:
            return

        for bank in banks:
            FastPaymentBank.objects.update_or_create(
                code=bank['code'],
                gateway=self.gateway,
                defaults={
                    'name': bank['name'],
                    'is_healthy_on_direct_debit': bank['is_healthy_on_direct_debit'],
                    'max_withdrawal_amount': bank['max_withdrawal_amount'],
                    'max_withdrawal_amount_per_transaction': bank['max_withdrawal_amount_per_transaction'],
                    'withdrawal_amount_currency': bank['withdrawal_amount_currency'],
                    'max_withdrawal_daily_count': bank['max_withdrawal_daily_count'],
                    'max_mandate_validity_duration': bank['max_mandate_validity_duration'],
                    'mandate_validity_duration_unit': bank['mandate_validity_duration_unit'],
                    'payer_authentication_type': bank['payer_authentication_type'],
                }
            )

    def get_banks(self):
        resp = self._collect_api(
            path=f'/v3/business/{self.gateway.business_name}/subscription/banks/actives',
            headers={'Accept': 'application/json', 'Content-Type': 'application/json'}
        )

        if resp.ok:
            return resp.data['result']['banks']

    def get_authorization_create_url(self, user: User, bank: FastPaymentBank):
        auth_token = self.get_authorization_token(user, bank)

        return f'https://subscription.vandar.io/authorizations/{auth_token}'

    def get_authorization_token(self, user: User, bank: FastPaymentBank):
        host_url = settings.HOST_URL
        payload = {
            "bank_code": bank.code,
            "mobile": user.phone,
            "callback_url": host_url + f'/api/v1/finance/fastPayment/authId/callback/vandar/',
            "count": (bank.max_withdrawal_daily_count or 100) * 30,
            "limit": bank.max_withdrawal_amount_per_transaction,
            "expiration_date": "2026-01-01",  # fix this
            "name": user.get_full_name(),
            "email": user.email,
            "wage_type": "APPLICATION_USER"
        }

        resp = self._collect_api(
            path=f'/v3/business/{self.gateway.business_name}/subscription/authorization/store',
            method='POST',
            headers={'Content-Type': 'application/json'},
            data=payload
        )

        if not resp.ok:
            raise ValueError(f"Failed to create subscription authorization: {resp.data}")

        if resp.data['status'] != 1:
            raise ValueError(f"Failed to create subscription authorization (status != 1): {resp.data}")

        auth_token = resp.data['result']['authorization']['token']

        auth_id = AuthorizationId.objects.get_or_create(user=user, bank=bank, defaults={
            'token': auth_token
        })

        if not auth_id:
            raise ValueError(f"Failed to create authorization id.")

        return auth_token

    def accept_authorization_id(self, authorization_id: str, token: str):
        auth_id = AuthorizationId.objects.filter(token=token)

        if not auth_id:
            raise ValueError(f'Failed to find authorization id')

        if auth_id.value:
            raise ValueError(f'Authorization id already accepted')

        auth_id.verified = True
        auth_id.auth_id = authorization_id
        auth_id.save(update_fields=['verified', 'auth_id'])
