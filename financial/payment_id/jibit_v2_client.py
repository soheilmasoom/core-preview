import logging
from datetime import datetime

import pytz
import requests

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId
from financial.payment_id.jibit_client import JibitClient
from ledger.utils.fields import PROCESS, INIT

logger = logging.getLogger(__name__)


class JibitClientV2(JibitClient):
    BASE_URL = 'https://napi.jibit.ir/cobank'

    def get_token(self, force_renew: bool = False):
        if not force_renew:
            if self._token:
                return self._token

        resp = requests.post(
            url=self.BASE_URL + '/v1/tokens/generate',
            json={
                'apiKey': self.gateway.payment_id_api_key,
                'secretKey': self.gateway.payment_id_secret,
                'scopes': ['VARIZ_PID', 'AUG_STATEMENT_VARIZ'],
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
            headers={'iban': self.gateway.iban},
            data={
                'pageNumber': 0,
                'pageSize': 100,
            })

        data = resp.get_success_data()

        for element in reversed(data.get("elements", [])):
            self._create_and_verify_payments_data(element)

    def _create_and_verify_payments_data(self, item: dict):
        ref_number = item['referenceNumber']

        payment_id = PaymentId.objects.filter(gateway=self.gateway, pay_id=item['payId']).first()

        if not payment_id:
            logger.info(f'Creating {ref_number} payment id request failed to due not found payment_id')
            logger.info(item)
            # self._fail(ref_number)
            return

        amount = item['creditAmount'] // 10
        fee = 0
        # fee = math.ceil(item['balance'] / 10_000_000) * 250

        if item['kytStatus'] == 'MATCH_IBAN_AND_NATIONAL_ID':
            status = PROCESS
        else:
            status = INIT

        deposit_time = datetime.strptime(item['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.utc)

        payment_request, created = PaymentIdRequest.objects.get_or_create(
            external_ref=ref_number,
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

        if status == PROCESS:
            self.verify_payment_request(payment_request)

    def verify_payment_request(self, payment_request: PaymentIdRequest):
        if payment_request.status not in PaymentIdRequest.PENDING_STATES:
            return

        resp = self._verify(payment_request.external_ref)

        if resp.success:
            payment_request.accept()

    def _verify(self, external_ref: str):
        return self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}/verify'
        )

    def _fail(self, external_ref: str):
        return self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}/fail'
        )

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
