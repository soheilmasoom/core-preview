import logging
from datetime import datetime, timedelta
from decimal import Decimal
from json import JSONDecodeError

import pytz
import requests
from django.utils import timezone

from accounts.verifiers.utils import ServerError
from financial.exceptions import ProviderError
from financial.interface.base_interface import BaseChannel, WalletDTO, WithdrawDTO
from financial.models import PaymentRequest
from financial.models.withdraw_request import BaseTransfer
from ledger.utils.fields import PENDING, DONE, CANCELED, UNKNOWN

logger = logging.getLogger(__name__)


class ZibalChannel(BaseChannel):
    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> dict:

        url = 'https://api.zibal.ir' + path

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
                'message': 'Zibal connection error'
            })

        if not resp_data['result'] == 1:
            print(resp_data)
            raise ServerError(resp_data)

        return resp_data['data']

    def get_wallet_data(self) -> WalletDTO:
        if not self.gateway.wallet_id:
            return WalletDTO(balance=0, free=0)

        balance_data = self.collect_api(f'/v1/wallet/balance', method='POST', data={
            "id": int(self.gateway.wallet_id)
        })

        resp = self.collect_api(
            path='/v1/wallet/list',
            timeout=5
        )

        total_wallet_irt_value = 0
        for wallet in resp:
            total_wallet_irt_value += Decimal(wallet['balance']) + Decimal(wallet.get('pendingPFAmount', 0)) + \
                                      Decimal(wallet.get('pendingCashIn', 0))

        return WalletDTO(
            balance=total_wallet_irt_value // 10,
            free=balance_data['withdrawableBalance'] // 10
        )

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        # paya_banks = []
        #
        # if transfer.bank_account.bank not in paya_banks:
        #     checkout_delay = -1
        #     status = DONE
        # else:
        #     checkout_delay = 0
        #     status = PENDING

        checkout_delay = 0
        status = PENDING

        try:
            data = self.collect_api('/v1/wallet/checkout/plus', method='POST', data={
                'id': int(self.gateway.wallet_id),
                'amount': transfer.amount * 10,
                'bankAccount': transfer.bank_account.iban,
                'uniqueCode': transfer.id,
                'wageFeeMode': 2,
                'checkoutDelay': checkout_delay,
                'showTime': True,
                'bank': 'smart',
            })
        except ServerError as e:
            resp = e.args[0]
            message = resp.get('message', '')

            if 'این درخواست تسویه قبلا ثبت شده است' in message:
                return WithdrawDTO(
                    tracking_id='',
                    status=PENDING,
                    receive_datetime=timezone.now() + timedelta(hours=3),
                    message=message,
                )
            elif 'این حساب مسدود شده و یا قابلیت واریز ندارد' in message:
                return WithdrawDTO(
                    tracking_id='',
                    status=CANCELED,
                    receive_datetime=None,
                    message=message,
                )
            elif 'باقی مانده سقف روزانه تسویه به این شبا' in message:
                return WithdrawDTO(
                    tracking_id='',
                    status=CANCELED,
                    receive_datetime=None,
                    message=message,
                )
            else:
                raise ProviderError(message)

        receive_datetime = datetime.strptime(data['predictedCheckoutDate'], '%Y/%m/%d-%H:%M:%S')

        return WithdrawDTO(
            tracking_id=data['id'],
            status=status,
            receive_datetime=receive_datetime.replace(tzinfo=pytz.utc).astimezone(),
            message=data.get('message', '')
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        try:
            data = self.collect_api(f'/v1/report/checkout/inquire', method='POST', data={
                "walletId": int(self.gateway.wallet_id),
                'uniqueCode': str(transfer.id)
            })
        except ServerError:
            return WithdrawDTO(
                tracking_id='',
                status=UNKNOWN
            )

        if 'details' in data:
            details = data['details'][0]
        else:
            details = {}

        if data['type'] == 'canceledCheckout':
            status = CANCELED
        elif data['type'] == 'checkoutQueue':
            status = PENDING
        else:
            mapping_status = {
                0: DONE,
                1: CANCELED,
                2: CANCELED,
            }
            status = details.get('checkoutStatus', PENDING)
            status = mapping_status.get(int(status), PENDING)

        return WithdrawDTO(
            tracking_id=details.get('refCode'),
            status=status
        )

    def get_transactions(self, merchant_id: str, status: int):
        return self.collect_api(
            path='/v1/gateway/report/transaction',
            method='POST',
            data={'merchantId': merchant_id, 'status': status},
            timeout=90
        )

    def update_missing_payments(self):
        if not self.gateway.withdraw_api_secret:
            return

        transactions = self.get_transactions(self.gateway.merchant_id, status=2)

        for t in transactions:
            authority = t['trackId']

            payment_request = PaymentRequest.objects.get(authority=authority)
            payment = payment_request.get_or_create_payment()

            payment_request.get_gateway().verify(payment)

