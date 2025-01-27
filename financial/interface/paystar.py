import hashlib
import hmac
import logging
from json import JSONDecodeError

import requests
from django.core.cache import cache

from accounts.verifiers.utils import Response, ServerError
from financial.interface.base_interface import BaseChannel, WalletDTO, WithdrawDTO
from financial.models.withdraw_request import BaseTransfer
from financial.utils.ach import next_ach_clear_time
from financial.utils.encryption import encrypt
from ledger.utils.fields import PENDING, DONE, CANCELED

logger = logging.getLogger(__name__)


class PaystarChannel(BaseChannel):
    BASE_URL = 'https://core.paystar.ir/api/wallet'

    def _refresh_token(self):
        key = 'paystar:token:refresh'
        if cache.get(key):
            return False

        logger.info('Refreshing paystar token')

        cache.set(key, 1, timeout=3600)

        resp = self.collect_api('/refresh-api-key', method='POST', data={
            'wallet_hashid': self.gateway.wallet_id,
            'password': self.gateway.withdraw_api_password,
            'refresh_token': self.gateway.withdraw_refresh_token,
            'sign': self._get_sign()
        })

        self.gateway.withdraw_api_key_encrypted = encrypt(resp.get_success_data()['api_key'])
        self.gateway.save(update_fields=['withdraw_api_key_encrypted'])

        return True

    def _get_token(self):
        return self.gateway.withdraw_api_key

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> Response:
        url = self.BASE_URL + path

        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': f'Bearer {self._get_token()}'},
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)
        except requests.exceptions.ConnectionError:
            logger.error('jibit connection error', extra={
                'url': url,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        try:
            resp_data = resp.json()
        except JSONDecodeError:
            resp_data = {'data': None}

        if self.verbose or not resp.ok:
            print('status', resp.status_code)
            print('data', resp_data)

        if resp.status_code == 400 and 'دسترسی نامعتبر' in resp_data.get('message', ''):
            if self._refresh_token():
                return self.collect_api(path, method, data, timeout)

        return Response(data=resp_data['data'], success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> WalletDTO:
        resp = self.collect_api('/wallets-balance', data={'wallet_hashid': self.gateway.wallet_id}).get_success_data()

        total_amount = resp['total_amount']
        available_amount = resp['available_amount']

        if isinstance(total_amount, str):
            total_amount = int(total_amount.replace(',', ''))

        if isinstance(available_amount, str):
            available_amount = int(available_amount.replace(',', ''))

        return WalletDTO(
            balance=total_amount // 10,
            free=available_amount // 10,
        )

    def _get_sign(self):
        sign_message = f'{self.gateway.wallet_id}#{self.gateway.withdraw_api_password}'
        return hmac.new(self.gateway.withdraw_api_secret.encode(), sign_message.encode(), hashlib.sha512).hexdigest()

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        transfers = [{
            'amount': transfer.amount * 10,
            'destination_number': transfer.bank_account.iban,
            'destination_firstname': transfer.bank_account.user.first_name,
            'destination_lastname': transfer.bank_account.user.last_name,
            'track_id': transfer.id,
        }]

        resp = self.collect_api('/create-settlement', method='POST', data={
            'wallet_hashid': self.gateway.wallet_id,
            'withdraw_type': 8,
            'transfers': transfers,
            'password': self.gateway.withdraw_api_password,
            'sign': self._get_sign()
        })

        if not resp.success:
            raise ServerError('Paystar withdraw error')

        return WithdrawDTO(
            status=PENDING,
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        resp = self.collect_api('/settlement-requests', method='GET', data={
            'wallet_hashid': self.gateway.wallet_id,
            'track_id': f'{self.gateway.wallet_id}*{transfer.id}*1'
        })

        data = resp.get_success_data()[0]

        mapping_status = {
            'pending': PENDING,
            'success': DONE,
            'failed': CANCELED
        }

        status = mapping_status.get(data['status'], PENDING)

        return WithdrawDTO(
            tracking_id=data['ref_code'],
            status=status,
        )
