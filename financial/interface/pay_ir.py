import logging
from datetime import datetime, timedelta

import requests
from django.utils import timezone

from accounts.verifiers.utils import ServerError
from financial.interface.base_interface import BaseChannel, WalletDTO, WithdrawDTO
from financial.models.withdraw_request import BaseTransfer
from financial.utils.withdraw_limit import is_holiday, time_in_range
from ledger.utils.fields import PENDING, DONE, CANCELED

logger = logging.getLogger(__name__)


class PayirChannel(BaseChannel):

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> dict:

        url = 'https://pay.ir' + path

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
        except requests.exceptions.ConnectionError:
            logger.error('pay.ir connection error', extra={
                'url': url,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        resp_data = resp.json()

        if self.verbose:
            print('status', resp.status_code)
            print('data', resp_data)

        if not resp.ok or not resp_data['success']:
            raise ServerError('Payir withdraw error')

        return resp_data['data']

    def get_wallet_data(self) -> WalletDTO:
        data = self.collect_api(f'/api/v2/wallets/{self.gateway.wallet_id}')['wallet']

        return WalletDTO(
            balance=data['balance'] // 10,
            free=data['cashoutableAmount'] // 10
        )

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        data = self.collect_api('/api/v2/cashouts', method='POST', data={
            'walletId': int(self.gateway.wallet_id),
            'amount': transfer.amount * 10,
            'name': transfer.bank_account.user.get_full_name(),
            'iban': transfer.bank_account.iban[2:],
            'uid': transfer.id,
        })

        return WithdrawDTO(
            tracking_id=str(data['cashout']['id']),
            status=PENDING,
            receive_datetime=self.get_estimated_receive_time(timezone.now())
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        data = self.collect_api(f'/api/v2/cashouts/track/{transfer.id}')

        mapping_status = {
            3: CANCELED,
            4: DONE,
            5: CANCELED

        }
        status = data['cashout']['status']

        return WithdrawDTO(
            status=mapping_status.get(int(status), PENDING)
        )

    def get_estimated_receive_time(self, created: datetime):
        request_date = created.astimezone()
        request_time = request_date.time()
        receive_time = request_date.replace(microsecond=0)

        if is_holiday(request_date):

            if time_in_range('00:00', '10:00', request_time):
                receive_time = receive_time.replace(hour=15, minute=00, second=00)
            else:
                receive_time += timedelta(days=1)

                if is_holiday(receive_time):
                    receive_time = receive_time.replace(hour=15, minute=00, second=00)
                else:
                    receive_time = receive_time.replace(hour=10, minute=30, second=00)

        else:
            if time_in_range('0:0', '0:30', request_time):
                receive_time = receive_time.replace(hour=10, minute=30, second=00)

            elif time_in_range('0:30', '10:30', request_time):
                receive_time = receive_time.replace(hour=14, minute=30, second=00)

            elif time_in_range('10:30', '13:23', request_time):
                receive_time = receive_time.replace(hour=19, minute=30, second=00)

            elif time_in_range('13:23', '18:30', request_time):
                receive_time += timedelta(days=1)
                receive_time = receive_time.replace(hour=4, minute=30, second=00)

            else:
                receive_time += timedelta(days=1)

                if is_holiday(receive_time):
                    receive_time = receive_time.replace(hour=14, minute=30, second=00)
                else:
                    receive_time = receive_time.replace(hour=10, minute=30, second=00)

        return receive_time

    # def get_total_wallet_irt_value(self):
    #     resp = self.collect_api(
    #         path='/api/v2/wallets',
    #         timeout=5
    #     )
    #
    #     total_wallet_irt_value = 0
    #     for wallet in resp['wallets']:
    #         total_wallet_irt_value += Decimal(wallet['balance'])
    #
    #     return total_wallet_irt_value // 10
