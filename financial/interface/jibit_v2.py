import logging
from json import JSONDecodeError

import requests
from urllib3.exceptions import ReadTimeoutError

from accounts.verifiers.utils import Response
from financial.exceptions import ProviderError
from financial.interface.base_interface import BaseChannel, WithdrawDTO, WalletDTO
from financial.models.withdraw_request import BaseTransfer
from financial.utils.ach import next_ach_clear_time
from financial.utils.jibit import get_jibit_error_message
from ledger.utils.fields import PENDING, DONE, CANCELED

logger = logging.getLogger(__name__)


class JibitChannelV2(BaseChannel):
    BASE_URL = 'https://napi.jibit.ir/cobank'
    _token = None

    def get_token(self, force_renew: bool = False):
        if not force_renew:
            if self._token:
                return self._token

        resp = requests.post(
            url=self.BASE_URL + '/v1/tokens/generate',
            json={
                'apiKey': self.gateway.withdraw_api_key,
                'secretKey': self.gateway.withdraw_api_secret,
                'scopes': ['SETTLEMENT'],
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            self._token = resp_data['accessToken']
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
            if self.verbose:
                print(data)
                print(resp_json)
        except JSONDecodeError:
            resp_json = None

        if not resp.ok:
            logger.info(f'{url} {resp.status_code}: {resp_json}')

        return Response(data=resp_json, success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> WalletDTO:
        return WalletDTO(
            balance=0,
            free=0
        )

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        resp = self._collect_api('/v1/orders/settlement', method='POST', data={
            'destinationIban': transfer.bank_account.iban,
            'amount': transfer.amount * 10,
            'recordTrackId': str(transfer.group_id),
            'transferType': 'NORMAL',
            'sourceIban': self.gateway.merchant_id,
            'requestDescription': 'پرداخت بابت برداشت کاربران'
        })

        if not resp.success:
            error = get_jibit_error_message(resp.data)
            message = error.message + f' ({error.code})'
            if resp.status_code == 500:
                return self.get_withdraw_status(transfer)
            else:
                raise ProviderError(message)

        if resp.data.get('referenceNumber', 0) == 0:
            raise ProviderError('Jibit submission failed')

        return WithdrawDTO(
            tracking_id='',
            status=PENDING,
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        resp = self._collect_api(f'/v1/orders/settlement/{transfer.group_id}')
        data = resp.get_success_data()

        mapping_status = {
            'CANCELLED': CANCELED,
            'TRANSFERRED': DONE,
            'CANCELLING': CANCELED,
            'FAILED': CANCELED,
            'IN_PROGRESS': PENDING,
            'FAILED_RECEIVED': CANCELED,
        }

        record = data['records'][0]

        tracking_id = record['referenceNumber'] or ''

        channel_status = record['state']
        status = mapping_status.get(channel_status, PENDING)

        return WithdrawDTO(
            tracking_id=tracking_id,
            status=status,
        )
