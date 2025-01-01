import logging
import math
import uuid

import jdatetime
import requests

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId
from financial.payment_id.jibit_client import JibitClient
from ledger.utils.fields import PROCESS, PENDING, CANCELED

logger = logging.getLogger(__name__)


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
        resp = self._collect_api(
            path=f'/v1/orders/aug-statement/{self.gateway.iban}/variz-pid/waitingForVerify',
            headers={'Iban': self.gateway.iban},
            data={
                'pageNumber': 1,
                'pageSize': 100,
            })

        if resp.status_code != 200:
            logger.error(f"Error while collecting Jibit payments: {resp.status_code}")
            return

        data = resp.data
        if not data['hasNext']:
            return

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

        assert user.national_code

        payment_id = PaymentId.objects.create(
            user=user,
            pay_id=user.national_code,
            verified=True,
            gateway=self.gateway,
        )

        return payment_id

    def check_payment_id_status(self, payment_id: PaymentId):
        return True
