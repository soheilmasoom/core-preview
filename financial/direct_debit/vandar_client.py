import logging
from datetime import datetime, timedelta
from json import JSONDecodeError

import requests
from django.conf import settings
from urllib3.exceptions import ReadTimeoutError

from accounts.models import User
from accounts.verifiers.jibit import Response
from financial.direct_debit.base_client import BaseClient
from financial.models.direct_debit_bank import DirectDebitBank
from financial.models.direct_debit_connection import DirectDebitConnection
from financial.models.direct_debit_request import DirectDebitRequest
from financial.utils.bank import get_bank_from_iban, get_bank_from_slug
from ledger.utils.fields import PROCESS

logger = logging.getLogger(__name__)


class ExternalAPIError(Exception):
    pass


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
            self.gateway.set_refresh_token(resp_data['refresh_token'])
            self._token = resp_data['access_token']
            print(resp_data['refresh_token'])
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
            bank_data = get_bank_from_iban(f'0000{bank["code"]}0')

            if not bank_data:
                logger.info(f'Bank exist in vandar but not in raastin: {bank}')
                continue

            DirectDebitBank.objects.update_or_create(
                bank=bank_data.slug,
                gateway=self.gateway,
                defaults={
                    'active': bank['is_healthy_on_direct_debit'],
                    'max_withdrawal_amount': bank['max_withdrawal_amount'] / 10,
                    'max_withdrawal_amount_per_transaction': bank['max_withdrawal_amount_per_transaction'] / 10,
                    'max_withdrawal_daily_count': bank['max_withdrawal_daily_count'],
                    'max_validity_duration_days': (bank['max_mandate_validity_duration'] * (
                        365 if bank['mandate_validity_duration_unit'] == 'YEAR' else 30)) or 365,
                    'kyc_type': bank['payer_authentication_type'],
                }
            )

    def get_banks(self):
        resp = self._collect_api(
            path=f'/v3/business/{self.gateway.business_name}/subscription/banks/actives',
            headers={'Accept': 'application/json', 'Content-Type': 'application/json'}
        )

        if resp.ok:
            return resp.data['result']['banks']

    def get_authorization_create_url(self, user: User, bank: DirectDebitBank):
        auth_token = self.get_authorization_token(user, bank)

        return f'https://subscription.vandar.io/authorizations/{auth_token}'

    def get_authorization_token(self, user: User, bank: DirectDebitBank):
        expiration_date = datetime.now() + timedelta(days=bank.max_validity_duration_days)
        bank_data = get_bank_from_slug(bank.bank)
        host_url = settings.HOST_URL

        payload = {
            "bank_code": bank_data.iban_code[:3],
            "mobile": user.phone,
            "callback_url": host_url + f'/api/v1/finance/directDebit/authId/callback/vandar/',
            "count": (bank.max_withdrawal_daily_count or 100) * 30,
            "limit": bank.max_withdrawal_amount_per_transaction,
            "expiration_date": expiration_date.strftime("%Y-%m-%d"),
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
            raise ExternalAPIError(f"ارتباط با وندار ناموفق بود: {resp.data.get('message', None)}")

        if resp.data['status'] != 1:
            raise ExternalAPIError(f"ارتباط با وندار ناموفق بود: {resp.data.get('message', None)}")

        auth_token = resp.data['result']['authorization']['token']

        connection = DirectDebitConnection.objects.get_or_create(user=user, bank=bank, defaults={
            'token': auth_token
        })

        if not connection:
            raise ExternalAPIError(f"شناسه مجوز ایجاد نشد.")

        return auth_token

    def accept_authorization_id(self, connection: DirectDebitConnection):
        resp = self._collect_api(
            path=f'/v3/business/{self.gateway.business_name}/subscription/authorization/{connection.auth_id}/verify',
            method='PATCH',
            headers={'Content-Type': 'application/json'},
        )

        if resp.ok and resp.data['status'] == 1:
            connection.verified = True
            connection.save(update_fields=['verified'])

        else:
            raise ExternalAPIError(f"ارتباط با وندار ناموفق بود: {resp.data.get('message', None)}")

    def cancel_authorization_id(self, auth_id: DirectDebitConnection):
        resp = self._collect_api(
            path=f'/v3/business/{self.gateway.business_name}/subscription/authorization/{auth_id.auth_id}',
            method='DELETE',
            headers={'Content-Type': 'application/json'},
        )

        if resp.ok and resp.data['status'] == 1:
            auth_id.deleted = True
            auth_id.save(update_fields=['deleted'])

        else:
            raise ExternalAPIError(f"ارتباط با وندار ناموفق بود: {resp.data.get('message', None)}")

    def create_payment_data(self, connection: DirectDebitConnection, amount):
        payload = {
            "authorization_id": connection.auth_id,
            "amount": str(amount),
        }

        resp = self._collect_api(
            path=f'/v3/business/{self.gateway.business_name}/subscription/withdrawal/store',
            method='POST',
            headers={'Content-Type': 'application/json'},
            data=payload
        )

        if resp.ok and resp.data['status'] == 1:
            fee = 0
            # fee = math.ceil(item['balance'] / 10_000_000) * 250
            payment_request = DirectDebitRequest.objects.create(
                owner=connection,
                gateway=self.gateway,
                amount=amount - fee,
                fee=fee,
                status=PROCESS,
            )

            return payment_request.accept()

        else:
            raise ExternalAPIError(f"ارتباط با وندار ناموفق بود: {resp.data.get('message', None)}")
