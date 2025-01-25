import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Union

import pytz
import requests
from django.utils import timezone

from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.models import User
from accounts.utils.similarity import clean_persian_word
from accounts.utils.telegram import send_system_message
from financial.exceptions import DuplicatedPaymentError
from financial.models import PaymentIdRequest, PaymentId, BankCard, BankAccount, PaymentIdGateway
from financial.parser.base_parser import TransactionInfo
from financial.payment_id.jibit_client import JibitClient
from financial.utils.date import parse_datetime
from ledger.utils.fields import INIT, CANCELED, REFUND

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
                'scopes': ['VARIZ_PID', 'AUG_STATEMENT_VARIZ', 'AUG_STATEMENT'],
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            self._token = resp_data['accessToken']
            return self._token

    def create_payments_requests(self):
        resp = self._collect_api(
            path=f'/v1/orders/aug-statement/{self.gateway.iban}/variz/waitingForVerify',
            headers={'iban': self.gateway.iban},
        )

        data = resp.get_success_data()

        for element in reversed(data.get("elements", [])):
            transaction = self._parse_transaction(element)
            self._process_new_deposit(transaction)

        recent_init = PaymentIdRequest.objects.filter(
            gateway=self.gateway,
            status=INIT,
            created__gt=timezone.now() - timedelta(hours=1)
        )

        for payment_request in recent_init:
            transaction = self._fetch_transaction(payment_request.external_ref)
            self._process_init_deposit(transaction)

    def _parse_transaction(self, data: dict) -> TransactionInfo:
        credit_amount = data['creditAmount'] // 10
        debit_amount = data['debitAmount'] // 10

        if credit_amount:
            amount = credit_amount
            deposit_type = TransactionInfo.DEPOSIT
        elif debit_amount:
            amount = debit_amount
            deposit_type = TransactionInfo.WITHDRAW
        else:
            raise NotImplementedError

        record_type = data['recordType']
        if record_type.startswith('VARIZ_'):
            record_type = record_type[6:]

        return TransactionInfo(
            reference_number=data['referenceNumber'],
            account_iban=data['accountIban'],
            bank_reference_number=data['bankReferenceNumber'] or '',
            bank_transaction_id=data['bankTransactionId'],
            amount=amount,
            deposit_type=deposit_type,
            balance=data['balance'] // 10,
            created=parse_datetime(data['createdAt']).astimezone(),
            deposited_at=datetime.strptime(data['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.utc),
            deposit_number=data['payId'] or '',
            raw_data=data['rawData'] or '',
            sender_identifier=data['sourceIdentifier'] or '',
            sender_iban=data['sourceIban'] or '',
            sender_name=clean_persian_word(data['sourceName'] or ''),
            record_type=record_type.lower(),
            receiver_iban=data['destinationIban'] or '',
            kyt_passed=data['kytStatus'] == 'MATCH_IBAN_AND_NATIONAL_ID',
            refund_type=data['refundType'] or '',
            refund_track_id=data['refundTrackId'] or ''
        )

    def _create_or_update_payment_request(self, transaction: TransactionInfo) -> PaymentIdRequest:
        assert transaction.receiver_iban == self.gateway.iban
        assert transaction.deposit_type == TransactionInfo.DEPOSIT

        ref_number = transaction.reference_number

        if PaymentIdRequest.objects.filter(
            bank_transaction_id=transaction.bank_transaction_id
        ).exclude(
            external_ref=ref_number
        ).exists():
            logger.info('Reject due to duplicate bank_transaction_id')
            self._fail(external_ref=ref_number)
            raise DuplicatedPaymentError

        user = self._get_owner(transaction)

        amount = transaction.amount
        fee = 0
        # fee = math.ceil(item['balance'] / 10_000_000) * 250

        payment_request_info = {
            'bank_ref': transaction.bank_reference_number,
            'bank_transaction_id': transaction.bank_transaction_id,
            'amount': amount - fee,
            'fee': fee,
            'balance': transaction.balance,
            'user': user,
            'sender_iban': transaction.sender_iban,
            'sender_name': transaction.sender_name,
            'sender_identifier': transaction.sender_identifier,
            'record_type': transaction.record_type,
            'kyt_passed': transaction.kyt_passed,
            'deposit_time': transaction.deposited_at,
            'raw_payment_id': transaction.deposit_number,
            'raw_data': transaction.raw_data,
            'refund_type': transaction.refund_type,
            'refund_track_id': transaction.refund_track_id,
        }

        existing = PaymentIdRequest.objects.filter(external_ref=ref_number).first()

        if not existing:
            return PaymentIdRequest.objects.create(
                external_ref=ref_number,
                status=INIT,
                gateway=self.gateway,
                **payment_request_info,
            )
        else:
            if existing.gateway != self.gateway:
                raise DuplicatedPaymentError

            PaymentIdRequest.objects.filter(external_ref=ref_number, gateway=self.gateway).update(**payment_request_info)
            return PaymentIdRequest.objects.filter(external_ref=ref_number).first()

    def _process_new_deposit(self, transaction: TransactionInfo) -> 'PaymentIdRequest':
        payment_request = self._process_init_deposit(transaction)

        if payment_request == INIT:
            self._decide_later(external_ref=payment_request.external_ref)

            send_system_message(
                message=f'PaymentId Request {payment_request} changed to INIT due to kyt failed',
                link=url_to_edit_object(payment_request),
            )

        return payment_request

    def _process_init_deposit(self, transaction: TransactionInfo) -> 'PaymentIdRequest':
        payment_request = self._create_or_update_payment_request(transaction)
        if payment_request.status != INIT:
            return payment_request

        ref_number = transaction.reference_number

        if transaction.refund_type or transaction.refund_track_id:
            payment_request.change_to_refund()
            self._fail(external_ref=ref_number)
            payment_request.refresh_from_db()

        elif payment_request.user:
            ignore_kyt = self.gateway.type != PaymentIdGateway.PAYMENT_ID or \
                         payment_request.record_type == PaymentIdRequest.CARD

            user_full_name = payment_request.user.get_full_name()

            if payment_request.kyt_passed or ignore_kyt or payment_request.sender_name == user_full_name:
                payment_request.accept()
                self._verify(external_ref=ref_number)
                payment_request.refresh_from_db()

        return payment_request

    def _verify(self, external_ref: str):
        return self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}/verify'
        )

    def _fail(self, external_ref: str):
        return self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}/fail'
        )

    def _decide_later(self, external_ref: str):
        return self._collect_api(
            f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}/to-be-decided'
        )

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        existing = PaymentId.objects.filter(user=user, gateway=self.gateway, deleted=False).first()
        if existing:
            return existing

        if user.level < User.LEVEL2 or not user.national_code:
            return

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
            while True:
                resp = self._collect_api(
                    path=f'/v1/orders/aug-statement/{self.gateway.iban}/variz/list',
                    headers={'iban': self.gateway.iban},
                    data={
                        'fromDate': str(from_date),
                        'toDate': str(tomorrow),
                        'pageNumber': page_number
                    })

                data = resp.get_success_data()

                for element in reversed(data.get("elements", [])):
                    transaction = self._parse_transaction(element)
                    self._process_init_deposit(transaction)

                if not data['hasNext']:
                    break

                page_number += 1

            from_date = tomorrow

    def _fetch_transaction(self, external_ref: str) -> TransactionInfo:
        resp = self._collect_api(f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{external_ref}')
        data = resp.get_success_data()
        return self._parse_transaction(data)

    def update_payment_request(self, payment_request: PaymentIdRequest) -> PaymentIdRequest:
        transaction = self._fetch_transaction(payment_request.external_ref)
        return self._process_init_deposit(transaction)

    def _get_owner(self, transaction: TransactionInfo) -> Union[User, None]:
        if self.gateway.type == PaymentIdGateway.PAYMENT_ID:
            deposit_number = transaction.deposit_number

            if deposit_number:
                payment_id = PaymentId.objects.filter(gateway=self.gateway, pay_id=deposit_number).first()

                if payment_id:
                    return payment_id.user

                user = User.objects.filter(level__gte=User.LEVEL2, national_code=deposit_number).first()

                if user:
                    return user

        if transaction.sender_identifier:
            if transaction.record_type == PaymentIdRequest.CARD:
                card = BankCard.live_objects.filter(card_pan=transaction.sender_identifier, verified=True).first()
                if card:
                    return card.user

            elif transaction.record_type in (PaymentIdRequest.ACH, PaymentIdRequest.RTGS, PaymentIdRequest.POL):
                bank_account = BankAccount.live_objects.filter(iban=transaction.sender_identifier, verified=True).first()
                if bank_account:
                    return bank_account.user

            elif transaction.record_type == PaymentIdRequest.INTERNAL:
                bank_account = BankAccount.live_objects.filter(deposit_address=transaction.sender_identifier, verified=True, bank=self.gateway.bank).first()
                if bank_account:
                    return bank_account.user

    def get_balance(self) -> Decimal:
        resp = self._collect_api(
            path=f'/v1/orders/aug-statement/{self.gateway.iban}/list',
            data={
                'fromDate': '2025-01-01',
                'toDate': str(date.today() + timedelta(days=2)),
                'pageSize': 1
            }
        )

        elements = resp.data['elements']
        if not elements:
            return Decimal(0)

        trx_data = elements[0]
        transaction = self._parse_transaction(trx_data)
        return Decimal(transaction.balance)

    def refund_payment_request(self, payment_request: PaymentIdRequest) -> bool:
        if payment_request.status not in (INIT, CANCELED):
            return False

        self._fail(external_ref=payment_request.external_ref)

        resp = self._collect_api(
            path=f'/v1/orders/aug-statement/{self.gateway.iban}/variz/{payment_request.external_ref}/full-refund',
            method='POST'
        )
        if not resp.ok:
            error = resp.data['errors'][0]['message']
            payment_request.add_comment(f'Refund failed due to jibit error: "{error}"')
            p = self.update_payment_request(payment_request)
            return p.status == REFUND

        data = resp.get_success_data()
        transaction = self._parse_transaction(data)

        if transaction.refund_track_id:
            payment_request.refund_track_id = transaction.refund_track_id
            payment_request.refund_type = transaction.refund_type
            payment_request.save(update_fields=['refund_track_id', 'refund_type'])
            payment_request.change_to_refund()
            return True
        else:
            return False

    def accept_payment_request(self, payment_request: PaymentIdRequest):
        payment_request.accept()
        self._verify(external_ref=payment_request.external_ref)

    def reject_payment_request(self, payment_request: PaymentIdRequest):
        payment_request.change_to_canceled()
        self._fail(external_ref=payment_request.external_ref)
