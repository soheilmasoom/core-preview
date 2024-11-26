import logging

import requests

from accounts.verifiers.utils import Response
from financial.interface.base_interface import WithdrawDTO, WalletDTO, BaseChannel
from financial.models.withdraw_request import BaseTransfer
from financial.utils.ach import next_ach_clear_time
from ledger.utils.fields import PENDING, DONE, CANCELED

logger = logging.getLogger(__name__)


class JibimoChannel(BaseChannel):

    STATUS_MAP = {
        'success': DONE,
        'wait': PENDING,
        'rejected': CANCELED,
        'reversed': CANCELED,
        'paying': PENDING,
        'not_sent': PENDING,
    }

    def _get_token(self):
        resp = requests.post('https://api.jibimo.com/v2/auth/token', headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }, json={
            'username': self.gateway.withdraw_api_key,
            'password': self.gateway.withdraw_api_password,
            'secret_key': self.gateway.withdraw_api_secret,
            'scopes': ['registered-user']
        })

        if resp.ok:
            resp = resp.json()
            return resp['token_type'] + ' ' + resp['access_token']

    def get_batch_id(self):
        gateway = self.gateway
        if not gateway.batch_id:
            resp = self.collect_api('/v2/batch-pay/create', method='POST', data={
                "title": "raastin_withdraw",
                "matching": False,
                "conversion": False,
                "validation": "active_account",
                "pay_after_validation": True
            })

            if resp.success:
                gateway.batch_id = resp.data['batch_id']
                gateway.save(update_fields=['batch_id'])

        return gateway.batch_id

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        batch = self.get_batch_id()
        assert batch, 'Unsuccessful batch creation attempt'

        resp = self.collect_api(f'/v2/batch-pay/{batch}/items/create', method='POST', data={
            "data": [{
                "uuid": str(transfer.group_id),
                "row": transfer.id,
                "name": transfer.bank_account.user.first_name,
                "family": transfer.bank_account.user.last_name,
                "amount": transfer.amount * 10,
                "iban": transfer.bank_account.iban,
                "account": transfer.bank_account.deposit_address,
                "national_code": transfer.bank_account.user.national_code
            }]
        })

        assert resp.success, 'Unsuccessful payment request'

        item_data = resp.data['items'][0]

        return WithdrawDTO(
            tracking_id=item_data['tracking_number'] or '',
            status=self.STATUS_MAP[item_data['pay_status']],
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        resp = self.collect_api(f'/v2/batch-pay/item/report?item_uuid={transfer.group_id}', method='GET')
        assert resp.success, 'Unsuccessful withdraw status collection attempt'

        return WithdrawDTO(
            tracking_id=resp.data['tracking_number'],
            status=self.STATUS_MAP[resp.data['pay_status']],
        )

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> Response:
        url = 'https://api.jibimo.com' + path

        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': self._get_token()},
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)
        except requests.exceptions.ConnectionError:
            logger.error('jibimo connection error', extra={
                'url': url,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        resp_data = resp.json()

        if self.verbose or not resp.ok:
            print('status', resp.status_code)
            print('data', resp_data)

        return Response(data=resp_data, success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> WalletDTO:
        resp = self.collect_api('/v2/business/refresh')
        user = resp.get_success_data()['user']

        balance = int(float(user['balance']) - float(user['reserved']))

        return WalletDTO(
            balance=balance,
            free=balance
        )
