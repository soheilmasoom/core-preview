import logging
from datetime import datetime
from json import JSONDecodeError
from typing import List

import requests
from django.utils import timezone
from urllib3.exceptions import ReadTimeoutError

from accounts.verifiers.utils import Response
from financial.exceptions import ProviderError
from financial.interface.base_interface import BaseChannel, WithdrawDTO, WalletDTO, WithdrawRefundedDTO
from financial.models.withdraw_request import BaseTransfer
from financial.utils.ach import next_ach_clear_time
from financial.utils.bank import BANK_INFO
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
                'scopes': ['VARIZ_PID', 'AUG_STATEMENT_VARIZ'],
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
        except JSONDecodeError:
            resp_json = None

        if not resp.ok:
            logger.info(f'{url} {resp.status_code}: {resp_json}')

        return Response(data=resp_json, success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> WalletDTO:
        resp = self._collect_api('/v2/balances')
        balance = 0
        free = 0

        for d in resp.get_success_data()['balances']:
            balance_type = d['balanceType']

            if balance_type == 'STL':
                free = d['amount']

            balance += d['amount']

        return WalletDTO(
            balance=balance // 10,
            free=free // 10
        )

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        if transfer.bank_account.bank in self.get_instant_banks():
            transfer_mode = 'NORMAL'
        else:
            transfer_mode = 'ACH'

        resp = self._collect_api('/v1/orders/settlement', method='POST', data={
            'submissionMode': 'TRANSFER',
            'batchID': 'wr-%s' % transfer.id,
            'transfers': [{
                'transferID': str(transfer.id),
                'destination': transfer.bank_account.iban,
                'destinationFirstName': transfer.bank_account.user.first_name,
                'destinationLastName': transfer.bank_account.user.last_name,
                'amount': transfer.amount,
                'currency': 'TOMAN',
                'cancellable': False,
                'transferMode': transfer_mode,
                'description': 'برداشت کاربر'
            }],
        })

        if not resp.success:
            code = resp.data['errors'][0]['code']
            if code == 'transfer.already_exists':
                return WithdrawDTO(
                    tracking_id='',
                    status=PENDING,
                )

            elif code == 'transfers.0.source_bank.not_supported':
                return WithdrawDTO(
                    tracking_id='',
                    status=CANCELED,
                    message=code,
                )

            else:
                raise ProviderError(code)

        if resp.data.get('submittedCount', 0) == 0:
            raise ProviderError('Jibit submission failed')

        return WithdrawDTO(
            tracking_id='',
            status=PENDING,
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        resp = self.collect_api('/v2/transfers?transferID={}'.format(transfer.id))
        data = resp.get_success_data()

        mapping_status = {
            'CANCELLED': CANCELED,
            'TRANSFERRED': DONE,
            'CANCELLING': CANCELED,
            'FAILED': CANCELED,
            'IN_PROGRESS': PENDING
        }

        transfer = data['transfers'][0]

        tracking_id = transfer['bankTransferID'] or ''

        channel_status = transfer['state']
        status = mapping_status.get(channel_status, PENDING)

        if tracking_id and status == PENDING:
            status = DONE

        return WithdrawDTO(
            tracking_id=tracking_id,
            status=status,
        )