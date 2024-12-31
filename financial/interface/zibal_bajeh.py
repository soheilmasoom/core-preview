import logging
from datetime import datetime
from json import JSONDecodeError

import pytz
import requests

from accounts.verifiers.utils import ServerError
from financial.exceptions import ProviderError
from financial.interface.base_interface import BaseChannel, WalletDTO, WithdrawDTO
from financial.models.withdraw_request import BaseTransfer
from ledger.utils.fields import PENDING, DONE, CANCELED, UNKNOWN

logger = logging.getLogger(__name__)


class ZibalBajehChannel(BaseChannel):
    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> dict:

        url = 'https://api.zibal.ir/ebank' + path

        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': self.gateway.withdraw_api_secret},
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)

            resp_data = resp.json()

        except (requests.exceptions.ConnectionError, JSONDecodeError, TimeoutError):
            raise ServerError({
                'message': 'Zibal bajeh connection error'
            })

        if self.verbose or not resp_data['result'] == 1:
            print(resp_data)
            raise ServerError(resp_data)

        return resp_data['data']

    def get_wallet_data(self) -> WalletDTO:
        balance_data = self.collect_api('/v1/account/balance/', method='GET', data={
            'accountId': self.gateway.withdraw_api_key
        })

        balance = balance_data['balance'] // 10

        return WalletDTO(
            balance=balance,
            free=balance
        )

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        data = self.collect_api('/v1/account/checkout/create/', method='POST', data={
            'accountId': self.gateway.withdraw_api_key,
            'amount': transfer.amount * 10,
            'iban': transfer.bank_account.iban,
            'uniqueCode': transfer.id,
            'delay': -1,  # -1 for instant, 0 for paya
        })

        checkouts = data['checkouts']

        if not checkouts:
            raise ProviderError

        checkout = checkouts[0]

        receive_datetime = datetime.strptime(checkout['settledAt'], '%Y/%m/%d-%H:%M:%S.%f').astimezone()

        return WithdrawDTO(
            tracking_id=checkout['refCode'] or '',
            status=PENDING,
            receive_datetime=receive_datetime.replace(tzinfo=pytz.utc).astimezone(),
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        data = self.collect_api(f'/v1/account/checkout/inquire/', method='GET', data={
            'accountId': self.gateway.withdraw_api_key,
            'uniqueCode': str(transfer.id)
        })

        checkouts = data['checkouts']

        if not checkouts:
            return WithdrawDTO(
                tracking_id='',
                status=UNKNOWN
            )

        checkout = checkouts[0]

        mapping_status = {
            3: DONE,
            4: CANCELED,
            5: CANCELED,
        }

        status = mapping_status.get(checkout['status'], PENDING)

        return WithdrawDTO(
            tracking_id=checkout['refCode'] or '',
            status=status
        )
