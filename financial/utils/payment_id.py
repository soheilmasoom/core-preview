import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Union

import pytz
import requests
from django.utils import timezone

from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.models import User
from accounts.utils.similarity import clean_persian_word, name_similarity
from accounts.utils.telegram import send_system_message
from financial.exceptions import DuplicatedPaymentError
from financial.models import PaymentIdRequest, PaymentId, BankCard, BankAccount, PaymentIdGateway
from financial.parser.base_parser import TransactionInfo
from financial.payment_id import BaseClient
from financial.payment_id.jibit_client import JibitClient
from financial.utils.date import parse_datetime
from financial.utils.jibit import get_jibit_error_message
from ledger.utils.fields import INIT, CANCELED, REFUND

logger = logging.getLogger(__name__)


def get_transaction_owner(gateway: PaymentIdGateway, transaction: TransactionInfo) -> Union[User, None]:
    if gateway.type == PaymentIdGateway.PAYMENT_ID:
        deposit_number = transaction.deposit_number

        if deposit_number:
            payment_id = PaymentId.objects.filter(gateway=gateway, pay_id=deposit_number).first()

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
            bank_account = BankAccount.live_objects.filter(deposit_address=transaction.sender_identifier, verified=True,
                                                           bank=gateway.bank).first()
            if bank_account:
                return bank_account.user


def create_or_update_payment_id_request(gateway: PaymentIdGateway, transaction: TransactionInfo) -> PaymentIdRequest:
    assert transaction.receiver_iban == gateway.iban
    assert transaction.deposit_type == TransactionInfo.DEPOSIT

    ref_number = transaction.reference_number

    if not transaction.bank_transaction_id:
        raise DuplicatedPaymentError

    if PaymentIdRequest.objects.filter(
        bank_transaction_id=transaction.bank_transaction_id
    ).exclude(
        external_ref=ref_number
    ).exists():
        logger.info('Reject due to duplicate bank_transaction_id')
        raise DuplicatedPaymentError

    user = get_transaction_owner(gateway, transaction)

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
            gateway=gateway,
            **payment_request_info,
        )
    else:
        if existing.gateway != gateway:
            raise DuplicatedPaymentError

        PaymentIdRequest.objects.filter(external_ref=ref_number, gateway=gateway).update(**payment_request_info)
        return PaymentIdRequest.objects.filter(external_ref=ref_number).first()
