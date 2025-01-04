import logging
from datetime import datetime, timedelta, date

import pytz
import requests

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId
# from financial.parser.base_parser import TransactionInfo
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
        )

        data = resp.get_success_data()
        count = 0

        for element in reversed(data.get("elements", [])):
            if self._create_and_verify_payments_data(element):
                count += 1

        logger.info(f'{count} payment requests created!')

    # def _parse_transaction(self, item: dict) -> TransactionInfo:
    #     credit_amount = item['creditAmount']
    #     debit_amount = item['debitAmount']
    #
    #     assert debit_amount == 0
    #
    #     return TransactionInfo(
    #         reference_number=item['referenceNumber'],
    #         account_iban=item['accountIban'],
    #         bank_reference_number=item['bankReferenceNumber'],
    #         bank_transaction_id=item['bankTransactionId'],
    #         amount=credit_amount,
    #         deposit_type=TransactionInfo.DEPOSIT,
    #         balance=item['balance'],
    #         created=datetime.strptime(item['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.utc),
    #         deposit_number=item['payId'],
    #         description=item['rawData'],
    #     )

    def _create_and_verify_payments_data(self, item: dict) -> bool:
        ref_number = item['referenceNumber']

        payment_id = PaymentId.objects.filter(gateway=self.gateway, pay_id=item['payId']).first()

        amount = item['creditAmount'] // 10
        fee = 0
        # fee = math.ceil(item['balance'] / 10_000_000) * 250

        if payment_id and item['kytStatus'] == 'MATCH_IBAN_AND_NATIONAL_ID':
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
        else:
            self._fail(external_ref=ref_number)

        return created

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

    def traverse_all_payment_requests(self):
        days_count = 10
        from_date = date.today() - timedelta(days=days_count)

        for i in range(days_count):
            tomorrow = from_date + timedelta(days=1)
            logger.info(f'Fetching payment requests of {from_date}')

            page_number = 0
            count = 0
            while True:
                resp = self._collect_api(
                    path=f'/v1/orders/aug-statement/{self.gateway.iban}/variz-pid/list',
                    headers={'iban': self.gateway.iban},
                    data={
                        'fromDate': str(from_date),
                        'toDate': str(tomorrow),
                        'pageNumber': page_number
                    })

                data = resp.get_success_data()

                for element in reversed(data.get("elements", [])):
                    if self._create_and_verify_payments_data(element):
                        count =+ 1

                if not data['hasNext']:
                    break

                page_number += 1

            logger.info(f'{count} payment requests created')
            from_date = tomorrow
