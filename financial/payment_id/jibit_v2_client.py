import logging
from datetime import datetime, timedelta, date

import pytz
import requests
from django.utils import timezone

from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.models import User
from accounts.utils.similarity import clean_persian_word
from accounts.utils.telegram import send_system_message
from financial.models import PaymentIdRequest, PaymentId
from financial.parser.base_parser import TransactionInfo
from financial.payment_id.jibit_client import JibitClient
from ledger.utils.fields import PROCESS, INIT, CANCELED

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
            transaction = self._parse_transaction(element)
            if self._create_and_verify_payments_data(transaction):
                count += 1

        logger.info(f'{count} payment requests created!')

    def _parse_transaction(self, item: dict) -> TransactionInfo:
        credit_amount = item['creditAmount']
        debit_amount = item['debitAmount']

        assert debit_amount == 0

        record_type = item['recordType']
        if record_type.startswith('VARIZ_'):
            record_type = record_type[6:]

        return TransactionInfo(
            reference_number=item['referenceNumber'],
            account_iban=item['accountIban'],
            bank_reference_number=item['bankReferenceNumber'],
            bank_transaction_id=item['bankTransactionId'],
            amount=credit_amount // 10,
            deposit_type=TransactionInfo.DEPOSIT,
            balance=item['balance'],
            created=datetime.strptime(item['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.utc),
            deposit_number=item['payId'],
            raw_data=item['rawData'],
            sender_identifier=item['sourceIdentifier'] or '',
            sender_iban=item['sourceIban'] or '',
            sender_name=clean_persian_word(item['sourceName'] or ''),
            record_type=record_type.lower(),
            receiver_iban=item['destinationIban'],
            kyt_passed=item['kytStatus'] == 'MATCH_IBAN_AND_NATIONAL_ID'
        )

    def _create_and_verify_payments_data(self, transaction: TransactionInfo) -> bool:
        assert transaction.receiver_iban == self.gateway.iban

        ref_number = transaction.reference_number

        payment_id = PaymentId.objects.filter(gateway=self.gateway, pay_id=transaction.deposit_number).first()

        amount = transaction.amount
        fee = 0
        # fee = math.ceil(item['balance'] / 10_000_000) * 250

        if payment_id and transaction.kyt_passed:
            status = PROCESS
        else:
            status = INIT

        if PaymentIdRequest.objects.filter(
            bank_transaction_id=transaction.bank_transaction_id
        ).exclude(
            external_ref=ref_number
        ).exists():
            logger.info('Reject due to duplicate bank_transaction_id')
            self._fail(external_ref=ref_number)
            return False

        payment_request, created = PaymentIdRequest.objects.get_or_create(
            external_ref=ref_number,
            defaults={
                'bank_ref': transaction.bank_reference_number,
                'bank_transaction_id': transaction.bank_transaction_id,
                'gateway': self.gateway,
                'amount': amount - fee,
                'fee': fee,
                'balance': transaction.balance,
                'status': status,
                'owner': payment_id,
                'sender_iban': transaction.sender_iban,
                'sender_name': transaction.sender_name,
                'sender_identifier': transaction.sender_identifier,
                'record_type': transaction.record_type,
                'kyt_passed': transaction.kyt_passed,
                'deposit_time': transaction.created,
                'raw_payment_id': transaction.deposit_number,
                'raw_data': transaction.raw_data,
            }
        )

        if status == PROCESS:  # kyt passed
            self.verify_payment_request(payment_request)
        elif payment_request.status == INIT:  # kyt not passed
            if transaction.created < timezone.now() - timedelta(minutes=120):  # give time to jibit to verify
                self._fail(external_ref=ref_number)
                send_system_message(
                    message=f'PaymentIdRequest {payment_request} changed to INIT due to kyt failed',
                    link=url_to_edit_object(payment_request),
                )
        else:  # kyt not passed, but handled manually
            if payment_request.status == CANCELED:
                self._fail(external_ref=ref_number)
            else:
                self._verify(external_ref=ref_number)

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

    def _traverse_all_payment_requests(self):
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
                    transaction = self._parse_transaction(element)
                    if self._create_and_verify_payments_data(transaction):
                        count =+ 1

                if not data['hasNext']:
                    break

                page_number += 1

            logger.info(f'{count} payment requests created')
            from_date = tomorrow

    def _get_payment_id_details(self, external_ref: str):
        return self._collect_api(f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}')
