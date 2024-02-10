import logging
import math
import time
import uuid
from datetime import timedelta
from json import JSONDecodeError

import jdatetime
import requests
from django.conf import settings
from django.utils import timezone
from urllib3.exceptions import ReadTimeoutError

from accounts.models import User
from accounts.verifiers.jibit import Response
from financial.models import BankAccount, PaymentIdRequest, PaymentId, Gateway
from financial.models.bank import GeneralBankAccount
from financial.utils.bank import get_bank
from ledger.utils.fields import PROCESS, PENDING, CANCELED

logger = logging.getLogger(__name__)


class BaseClient:
    def __init__(self, gateway):
        self.gateway = gateway

    def create_payment_id(self, user: User) -> PaymentId:
        raise NotImplementedError

    def create_payment_request(self, external_ref: str) -> PaymentIdRequest:
        raise NotImplementedError

    def verify_payment_request(self, payment_request: PaymentIdRequest):
        raise NotImplementedError

    def create_missing_payment_requests(self):
        pass

    def create_missing_payment_requests_from_list(self):
        pass

    def check_payment_id_status(self, payment_id: PaymentId):
        raise NotImplementedError


class JibitClient(BaseClient):
    BASE_URL = 'https://napi.jibit.cloud/pip'
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

    def _collect_api(self, path: str, method: str = 'GET', data: dict = None) -> Response:
        if data is None:
            data = {}

        url = self.BASE_URL + path

        token = self._get_token()

        if not token:
            return Response(None, False, status_code=0)

        request_kwargs = {
            'url': url,
            'timeout': 30,
            'headers': {'Authorization': 'Bearer ' + token},
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
    
    def create_payment_id(self, user: User) -> PaymentId:
        existing = PaymentId.objects.filter(user=user, gateway=self.gateway, deleted=False).first()
        if existing:
            return existing

        host_url = settings.HOST_URL

        bank_accounts = BankAccount.objects.filter(user=user, verified=True)
        ibans = list(bank_accounts.values_list('iban', flat=True))

        owners = bank_accounts.order_by('owners')[0].owners
        owner = owners[0]
        owner_full_name = owner['firstName'] + ' ' + owner['lastName']

        group_id = uuid.uuid4()

        resp = self._collect_api('/v1/paymentIds', method='POST', data={
            'callbackUrl': host_url + f'/api/v1/finance/paymentId/callback/jibit/',
            'merchantReferenceNumber': str(group_id),
            'userFullName': owner_full_name,
            'userIbans': ibans,
            'userMobile': '09121234567',
        })

        assert resp.success

        destination, _ = GeneralBankAccount.objects.get_or_create(
            iban=resp.data['destinationIban'],
            defaults={
                'name': resp.data['destinationOwnerName'],
                'deposit_address': resp.data['destinationDepositNumber'],
                'bank': get_bank(swift_code=resp.data['destinationBank']).slug,
            }
        )

        payment_id = PaymentId.objects.create(
            user=user,
            gateway=self.gateway,
            pay_id=resp.data['payId'],
            group_id=group_id,
            verified=resp.data['registryStatus'] == 'VERIFIED',
            destination=destination,
            provider_status=resp.data['registryStatus'],
            provider_reason=resp.data.get('failReason') or '',
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
        payment_id = PaymentId.objects.get(pay_id=data['paymentId'], group_id=merchant_ref)
        deposit_time = jdatetime.datetime.strptime(data['rawBankTimestamp'], '%Y/%m/%d %H:%M:%S').togregorian().astimezone()

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

    def create_missing_payment_requests(self):
        resp = self._collect_api(f'/v1/payments/waitingForVerify?pageNumber=0&pageSize=100')

        for data in resp.get_success_data()['content']:
            self._create_and_verify_payment_data(data)

    def create_missing_payment_requests_from_list(self):
        now = timezone.now().astimezone().date() + timedelta(days=1)
        resp = self._collect_api(f'/v1/payments/list?fromDate={now - timedelta(days=7)}&toDate={now}')

        for data in resp.get_success_data()['content']:
            self._create_and_verify_payment_data(data)


class MockClient(BaseClient):
    def create_payment_id(self, user: User) -> PaymentId:
        destination, _ = GeneralBankAccount.objects.get_or_create(
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
                'destination': destination
            }
        )

        return pay_id

    def check_payment_id_status(self, payment_id: PaymentId):
        payment_id.verified = True
        payment_id.save(update_fields=['verified'])


def get_payment_id_client(gateway: Gateway) -> BaseClient:
    if settings.DEBUG_OR_TESTING_OR_STAGING:
        return MockClient(gateway)

    assert gateway.type == Gateway.JIBIT

    return JibitClient(gateway)
