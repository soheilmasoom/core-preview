import logging
import math
import time
import uuid
from json import JSONDecodeError
from typing import Union

import jdatetime
import requests
from decouple import config
from django.conf import settings
from urllib3.exceptions import ReadTimeoutError

from accounts.models import User
from accounts.verifiers.jibit import Response
from financial.models import BankAccount, PaymentIdRequest, PaymentId, PaymentIdGateway
from ledger.utils.fields import PROCESS, PENDING, CANCELED

logger = logging.getLogger(__name__)


class BaseClient:
    def __init__(self, gateway: PaymentIdGateway):
        self.gateway = gateway

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        raise NotImplementedError

    def create_payment_request(self, external_ref: str) -> PaymentIdRequest:
        raise NotImplementedError

    def verify_payment_request(self, payment_request: PaymentIdRequest):
        raise NotImplementedError

    def check_payment_id_status(self, payment_id: PaymentId):
        raise NotImplementedError

    def create_payments_requests(self):
        pass


class JibitClient(BaseClient):
    BASE_URL = 'https://napi.jibit.ir/pip'
    _token = None

    def _get_token(self, force_renew: bool = False):
        if not force_renew:
            if self._token:
                return self._token

        resp = requests.post(
            url=self.BASE_URL + '/v1/tokens/generate',
            json={
                'apiKey': self.gateway.payment_id_api_key,
                'secretKey': self.gateway.payment_id_secret,
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

        token = self._get_token()

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

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        existing = PaymentId.objects.filter(user=user, gateway=self.gateway, deleted=False).first()
        if existing:
            return existing

        host_url = settings.HOST_URL

        bank_accounts = BankAccount.objects.filter(user=user, verified=True, deleted=False)
        ibans = list(bank_accounts.values_list('iban', flat=True))

        assert ibans

        if not full_name:
            owners = bank_accounts.order_by('owners')[0].owners
            if owners:
                owner = owners[0]
                full_name = owner['firstName'] + ' ' + owner['lastName']
            else:
                full_name = user.get_full_name()

        group_id = uuid.uuid4()

        resp = self._collect_api('/v1/paymentIds', method='POST', data={
            'callbackUrl': host_url + f'/api/v1/finance/paymentId/callback/jibit/',
            'merchantReferenceNumber': str(group_id),
            'userFullName': full_name,
            'userIbans': ibans,
            'userMobile': '09121234567',
        })

        if not resp.ok:
            return

        payment_id = PaymentId.objects.create(
            user=user,
            pay_id=resp.data['payId'],
            group_id=group_id,
            verified=resp.data['registryStatus'] == 'VERIFIED',
            gateway=self.gateway,
            provider_status=resp.data['registryStatus'],
            provider_reason=resp.data.get('failReason') or '',
            full_name=full_name,
        )

        if not payment_id.verified:
            verified = self.check_payment_id_status(payment_id)

            for i in range(4):
                if verified:
                    break

                time.sleep(5)
                verified = self.check_payment_id_status(payment_id)

        return payment_id

    def update_payment_id(self, payment_id: PaymentId):
        raise NotImplementedError

    def check_payment_id_status(self, payment_id: PaymentId):
        resp = self._collect_api(
            path=f'/v1/paymentIds/{payment_id.group_id}',
        )

        payment_id.verified = resp.data['registryStatus'] == 'VERIFIED'
        payment_id.provider_status = resp.data['registryStatus']
        payment_id.provider_reason = resp.data.get('failReason') or ''

        payment_id.save(update_fields=['verified', 'provider_status', 'provider_reason'])

        return payment_id.verified

    def _create_and_verify_payment_data(self, data: dict):
        merchant_ref = data['merchantReferenceNumber']

        try:
            merchant_ref = uuid.UUID(merchant_ref)
        except ValueError:
            self._collect_api(f'/v1/payments/{merchant_ref}/fail')
            return

        payment_id = PaymentId.objects.get(pay_id=data['paymentId'], group_id=merchant_ref)
        deposit_time = jdatetime.datetime.strptime(data['rawBankTimestamp'],
                                                   '%Y/%m/%d %H:%M:%S').togregorian().astimezone()

        if data['status'] == 'SUCCESSFUL':
            status = PENDING
        else:
            status = PROCESS

        amount = data['amount'] // 10
        fee = math.ceil(data['amount'] / 10_000_000) * 250

        payment_request, created = PaymentIdRequest.objects.get_or_create(
            external_ref=data['externalReferenceNumber'],
            defaults={
                'bank_ref': data['bankReferenceNumber'],
                'amount': amount - fee,
                'fee': fee,
                'status': status,
                'owner': payment_id,
                'source_iban': data['sourceIdentifier'],
                'deposit_time': deposit_time,
            }
        )

        if not created and payment_request.status == PENDING:
            return

        if data['status'] == 'WAITING_FOR_MERCHANT_VERIFY':
            self.verify_payment_request(payment_request)

        # if payment_request.status == PENDING:
        #     send_system_message("New payment id request", link=url_to_admin_list(payment_request))

        return payment_request

    def create_payment_request(self, external_ref: str) -> PaymentIdRequest:
        resp = self._collect_api(f'/v1/paymentIds/{external_ref}')
        return self._create_and_verify_payment_data(resp.data)

    def verify_payment_request(self, payment_request: PaymentIdRequest):
        if payment_request.status != PROCESS:
            return

        resp = self._collect_api(f'/v1/payments/{payment_request.external_ref}/verify')

        if resp.success:
            payment_request.status = PENDING
            payment_request.save(update_fields=['status'])
            payment_request.accept()

    def reject_payment_request(self, payment_request: PaymentIdRequest):
        if payment_request.status != PROCESS:
            return

        resp = self._collect_api(f'/v1/payments/{payment_request.external_ref}/fail')

        if resp.success:
            payment_request.status = CANCELED
            payment_request.save(update_fields=['status'])
            payment_request.reject()

    def create_payments_requests(self):
        resp = self._collect_api(f'/v1/payments/waitingForVerify?pageNumber=0&pageSize=100')

        for data in resp.get_success_data()['content']:
            self._create_and_verify_payment_data(data)


class MockClient(BaseClient):
    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        destination, _ = PaymentIdGateway.objects.get_or_create(
            iban='IR760120020000008992439961',
            defaults={
                'name': 'ایوان رایان پیام',
                'bank': 'MELLAT',
                'deposit_address': '8992439961'
            }
        )

        pay_id, _ = PaymentId.objects.get_or_create(
            gateway=self.gateway,
            user=user,
            defaults={
                'pay_id': f'1111100000{user.id}',
                'gateway': destination
            }
        )

        return pay_id

    def check_payment_id_status(self, payment_id: PaymentId):
        payment_id.verified = True
        payment_id.save(update_fields=['verified'])


class JibitClientV2(JibitClient):
    BASE_URL = 'https://napi.jibit.ir/cobank/'

    def _get_token(self, force_renew: bool = False):
        if not force_renew:
            if self._token:
                return self._token

        resp = requests.post(
            url=self.BASE_URL + '/v1/tokens/generate',
            json={
                'apiKey': self.gateway.payment_id_api_key,
                'secretKey': self.gateway.payment_id_secret,
                'Scope': 'PID_VARIZ',
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            self._token = resp_data['accessToken']
            return self._token

    def create_payments_requests(self):
        page_number = 1
        page_size = config('JIBIT_PAGE_SIZE', cast=int, default=100)

        while True:
            resp = self._collect_api(
                path=f'/v1/orders/aug-statement/{self.gateway.iban}/variz-pid/waitingForVerify',
                headers={'Iban': self.gateway.iban},
                data={
                    'pageNumber': page_number,
                    'pageSize': page_size,
                })

            if resp.status_code != 200:
                logger.error(f"Error while collecting Jibit payments: {resp.status_code}, {resp.text}")
                break

            data = resp.json()
            if not data['hasNext']:
                break

            elements = data.get("elements", [])

            self._create_and_verify_payments_data(elements)

    def _create_and_verify_payments_data(self, data: list):
        payIds = [item['payId'] for item in data]
        users_map = {user.national_code: user for user in User.objects.filter(national_code__in=payIds)}

        for item in data:
            payment_id = PaymentId.objects.get_or_create(pay_id=item['payId'], defaults={
                'user': users_map[item['payId']],
                'group_id': uuid.uuid4(),
                'verified': True,
                'gateway': self.gateway,
                'provider_status': item['merchantVerificationStatus'],
                'provider_reason': '',
                'full_name': '',
            })

            merchant_ref = item['referenceNumber']

            try:
                merchant_ref = uuid.UUID(merchant_ref)
            except ValueError:
                self._collect_api(f'/v1/orders/aug-statement/{self.gateway.iban}/{merchant_ref}/fail')
                return

            amount = item['balance'] // 10
            fee = math.ceil(item['balance'] / 10_000_000) * 250

            if item['merchantVerificationStatus'] == 'SUCCESSFUL':
                status = PENDING
            else:
                status = PROCESS

            deposit_time = jdatetime.datetime.strptime(item['rawBankTimestamp'],
                                                       '%Y/%m/%d %H:%M:%S').togregorian().astimezone()

            payment_request, created = PaymentIdRequest.objects.get_or_create(
                external_ref=item['referenceNumber'],
                defaults={
                    'bank_ref': item['bankReferenceNumber'],
                    'amount': amount - fee,
                    'fee': fee,
                    'status': status,
                    'owner': payment_id,
                    'source_iban': item['sourceIdentifier'],
                    'deposit_time': deposit_time,
                }
            )

            if not created and payment_request.status == PENDING:
                return

            if item['merchantVerificationStatus'] == 'WAITING_FOR_MERCHANT_VERIFY':
                self.verify_payment_request(payment_request)

    def verify_payment_request(self, payment_request: PaymentIdRequest):
        if payment_request.status != PROCESS:
            return

        resp = self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway}/{payment_request.external_ref}/verify')

        if resp.success:
            payment_request.status = PENDING
            payment_request.save(update_fields=['status'])
            payment_request.accept()

    def reject_payment_request(self, payment_request: PaymentIdRequest):
        if payment_request.status != PROCESS:
            return

        resp = self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway.iban}/{payment_request.external_ref}/fail')

        if resp.success:
            payment_request.status = CANCELED
            payment_request.save(update_fields=['status'])
            payment_request.reject()

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        existing = PaymentId.objects.filter(user=user, gateway=self.gateway, deleted=False).first()
        if existing:
            return existing

        payment_id = PaymentId.objects.create(
            user=user,
            pay_id=user.national_code,
            verified=True,
            gateway=self.gateway,
        )

        return payment_id

    def check_payment_id_status(self, payment_id: PaymentId):
        return True


_CLIENTS = {
    PaymentIdGateway.JIBIT_OLD: JibitClient,
    PaymentIdGateway.JIBIT: JibitClientV2,
}


def get_payment_id_client(gateway: PaymentIdGateway) -> Union[BaseClient, None]:
    if settings.DEBUG_OR_TESTING_OR_STAGING:
        return MockClient(gateway)

    client = _CLIENTS.get(gateway.type, None)
    if client is None:
        return None

    return client(gateway)
