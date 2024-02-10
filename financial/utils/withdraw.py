import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Union

import pytz
import requests
from django.core.cache import cache
from django.utils import timezone

from accounts.verifiers.utils import Response
from financial.models import Gateway, PaymentRequest
from financial.models.withdraw_request import BaseTransfer
from financial.utils.ach import next_ach_clear_time
from financial.utils.encryption import encrypt
from financial.utils.withdraw_limit import is_holiday, time_in_range
from ledger.utils.fields import PENDING, DONE, CANCELED

logger = logging.getLogger(__name__)


class ServerError(Exception):
    pass


class ProviderError(Exception):
    pass


class NoChannelError(Exception):
    pass


@dataclass
class Wallet:
    balance: int
    free: int


@dataclass
class Withdraw:
    tracking_id: str
    status: str
    receive_datetime: Union[datetime, None] = None
    message: str = ''


class FiatWithdraw:
    def __init__(self, gateway: Gateway, verbose: bool = False):
        self.gateway = gateway
        self.verbose = verbose

    @classmethod
    def get_withdraw_channel(cls, gateway: Gateway, verbose: bool = False) -> 'FiatWithdraw':
        mapping = {
            Gateway.PAYIR: PayirChannel,
            Gateway.ZIBAL: ZibalChannel,
            Gateway.ZARINPAL: ZarinpalChannel,
            Gateway.JIBIT: JibitChannel,
            Gateway.JIBIMO: JibimoChannel,
            Gateway.PAYSTAR: PaystarChannel,
        }

        channel_class = mapping.get(gateway.type)
        if not channel_class:
            raise NoChannelError

        return channel_class(gateway, verbose)

    def create_withdraw(self, transfer: BaseTransfer) -> Withdraw:
        raise NotImplementedError

    def get_withdraw_status(self, transfer: BaseTransfer) -> Withdraw:
        raise NotImplementedError

    def get_wallet_data(self) -> Wallet:
        raise NotImplementedError

    def update_missing_payments(self, gateway: Gateway):
        pass

    def get_instant_banks(self, gateway: Gateway):
        pass

    def is_active(self):
        return bool(self.gateway.withdraw_api_secret_encrypted)


class PayirChannel(FiatWithdraw):

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

    def get_wallet_data(self) -> Wallet:
        data = self.collect_api(f'/api/v2/wallets/{self.gateway.wallet_id}')['wallet']

        return Wallet(
            balance=data['balance'] // 10,
            free=data['cashoutableAmount'] // 10
        )

    def create_withdraw(self, transfer: BaseTransfer) -> Withdraw:
        data = self.collect_api('/api/v2/cashouts', method='POST', data={
            'walletId': int(self.gateway.wallet_id),
            'amount': transfer.amount * 10,
            'name': transfer.bank_account.user.get_full_name(),
            'iban': transfer.bank_account.iban[2:],
            'uid': transfer.id,
        })

        return Withdraw(
            tracking_id=str(data['cashout']['id']),
            status=PENDING,
            receive_datetime=self.get_estimated_receive_time(timezone.now())
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> Withdraw:
        data = self.collect_api(f'/api/v2/cashouts/track/{transfer.id}')

        mapping_status = {
            3: CANCELED,
            4: DONE,
            5: CANCELED

        }
        status = data['cashout']['status']

        return Withdraw(
            tracking_id='',
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


class ZibalChannel(FiatWithdraw):

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
        except requests.exceptions.ConnectionError:
            logger.error('zibal connection error', extra={
                'url': url,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        resp_data = resp.json()

        if not resp_data['result'] == 1:
            print(resp_data)
            raise ServerError(resp_data)

        return resp_data['data']

    def get_wallet_data(self) -> Wallet:
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

        return Wallet(
            balance=total_wallet_irt_value // 10,
            free=balance_data['withdrawableBalance'] // 10
        )

    def create_withdraw(self, transfer: BaseTransfer) -> Withdraw:
        paya_banks = []

        if transfer.bank_account.bank not in paya_banks:
            checkout_delay = -1
            status = DONE
        else:
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
                return Withdraw(
                    tracking_id='',
                    status=PENDING,
                    receive_datetime=timezone.now() + timedelta(hours=3),
                    message=message,
                )
            elif 'این حساب مسدود شده و یا قابلیت واریز ندارد' in message:
                return Withdraw(
                    tracking_id='',
                    status=CANCELED,
                    receive_datetime=None,
                    message=message,
                )
            elif 'باقی مانده سقف روزانه تسویه به این شبا' in message:
                return Withdraw(
                    tracking_id='',
                    status=CANCELED,
                    receive_datetime=None,
                    message=message,
                )
            else:
                raise ProviderError(message)

        receive_datetime = datetime.strptime(data['predictedCheckoutDate'], '%Y/%m/%d-%H:%M:%S')

        return Withdraw(
            tracking_id=data['id'],
            status=status,
            receive_datetime=receive_datetime.replace(tzinfo=pytz.utc).astimezone()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> Withdraw:
        data = self.collect_api(f'/v1/report/checkout/inquire', method='POST', data={
            "walletId": int(self.gateway.wallet_id),
            'uniqueCode': str(transfer.id)
        })

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

        return Withdraw(
            tracking_id=details.get('refCode'),
            status=status
        )

    def get_transactions(self, merchant_id: str, status: int):
        return self.collect_api(
            path='/v1/gateway/report/transaction',
            method='POST',
            data={'merchantId': merchant_id, 'status': status},
            timeout=45
        )

    def update_missing_payments(self, gateway: Gateway):
        transactions = self.get_transactions(gateway.merchant_id, status=2)

        for t in transactions:
            authority = t['trackId']

            payment_request = PaymentRequest.objects.get(authority=authority)
            payment = payment_request.get_or_create_payment()

            payment_request.get_gateway().verify(payment)


class ZarinpalChannel(FiatWithdraw):
    pass


class JibitChannel(FiatWithdraw):
    BASE_URL = 'https://napi.jibit.ir/trf'
    INSTANT_BANKS = ['MELLI', 'RESALAT', 'KESHAVARZI', 'SADERAT', 'EGHTESAD_NOVIN', 'SHAHR', 'SEPAH',
                     'AYANDEH', 'SAMAN', 'TEJARAT', 'PARSIAN']

    def _get_token(self):
        resp = requests.post(
            url=self.BASE_URL + '/v2/tokens/generate',
            json={
                'apiKey': self.gateway.withdraw_api_key,
                'secretKey': self.gateway.withdraw_api_secret,
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            return resp_data['accessToken']

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> Response:
        url = 'https://napi.jibit.ir/trf' + path
        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': 'Bearer ' + self._get_token()},
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

        resp_data = resp.json()

        if self.verbose or not resp.ok:
            print('status', resp.status_code)
            print('data', resp_data)

        return Response(data=resp_data, success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> Wallet:
        resp = self.collect_api('/v2/balances')
        balance = 0
        free = 0

        for d in resp.get_success_data()['balances']:
            balance_type = d['balanceType']

            if balance_type == 'STL':
                free = d['amount']

            balance += d['amount']

        return Wallet(
            balance=balance // 10,
            free=free // 10
        )

    def create_withdraw(self, transfer: BaseTransfer) -> Withdraw:

        if transfer.bank_account.bank in self.INSTANT_BANKS:
            transfer_mode = 'NORMAL'
        else:
            transfer_mode = 'ACH'

        resp = self.collect_api('/v2/transfers', method='POST', data={
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
            if resp.data['errors'][0]['code'] == 'transfer.already_exists':
                return Withdraw(
                    tracking_id='',
                    status=PENDING,
                )

            else:
                raise ServerError('Jibit withdraw error')

        if resp.data.get('submittedCount', 0) == 0:
            raise ServerError('Jibit submission failed')

        return Withdraw(
            tracking_id='',
            status=PENDING,
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> Withdraw:
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

        return Withdraw(
            tracking_id=tracking_id,
            status=status,
        )


class JibimoChannel(FiatWithdraw):

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

    def create_withdraw(self, transfer: BaseTransfer) -> Withdraw:
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

        return Withdraw(
            tracking_id=item_data['tracking_number'] or '',
            status=self.STATUS_MAP[item_data['pay_status']],
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> Withdraw:
        resp = self.collect_api(f'/v2/batch-pay/item/report?item_uuid={transfer.group_id}', method='GET')
        assert resp.success, 'Unsuccessful withdraw status collection attempt'

        return Withdraw(
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

    def get_wallet_data(self) -> Wallet:
        resp = self.collect_api('/v2/business/refresh')
        user = resp.data['user']

        balance = int(float(user['balance']) - float(user['reserved']))

        return Wallet(
            balance=balance,
            free=balance
        )


class PaystarChannel(FiatWithdraw):
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
            'headers': {'Authorization': 'Bearer ' + self._get_token()},
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

        resp_data = resp.json()

        if self.verbose or not resp.ok:
            print('status', resp.status_code)
            print('data', resp_data)

        if resp.status_code == 400 and 'دسترسی نامعتبر' in resp_data.get('message', ''):
            if self._refresh_token():
                return self.collect_api(path, method, data, timeout)

        return Response(data=resp_data['data'], success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> Wallet:
        resp = self.collect_api('/wallets-balance', data={'wallet_hashid': self.gateway.wallet_id}).get_success_data()

        return Wallet(
            balance=int(resp['total_amount'].replace(',', '')) // 10,
            free=int(resp['available_amount'].replace(',', '')) // 10,
        )

    def _get_sign(self):
        sign_message = f'{self.gateway.wallet_id}#{self.gateway.withdraw_api_password}'
        return hmac.new(self.gateway.withdraw_api_secret.encode(), sign_message.encode(), hashlib.sha512).hexdigest()

    def create_withdraw(self, transfer: BaseTransfer) -> Withdraw:
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

        return Withdraw(
            tracking_id='',
            status=PENDING,
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> Withdraw:
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

        return Withdraw(
            tracking_id=data['ref_code'],
            status=status,
        )
