import dataclasses
import re

from accounts.utils.similarity import clean_persian_word
from financial.exceptions import ParseError

PARSIAN_PATTERNS = {
    # 'ach': [
    #     re.compile(r'(?P<deposit_type>واریز|برداشت) (?P<transfer_type>پایا) با مشخصات : رهگیری: (?P<tracking_id>\d+) شناسه پرداخت: (?P<deposit_number>EMPTY|\d+) شناسه تراکنش: (?P<transaction_id>[0-9a-zA-Z.-_]+) شرح: (?P<description>[\w-]+) نام: (?P<sender_name>.*) شبا: (?P<sender_id>IR\d+) - (?P<sender_bank>.*)'),
    # ],
    #
    # 'pol': [
    #     re.compile(r'تراکنش (?P<transfer_type>پل) به مشخصات با کد رهگیری (?P<tracking_id>\d+)، شناسه پرداخت (?P<deposit_number>EMPTY|\d+)، به نام (?P<sender_name>.*) و شماره شبا (?P<sender_id>IR\d+) - بانک (?P<sender_bank>.*)'),
    # ],
    #
    # 'internal': [
    #     re.compile('انتقال وجه از طریق (?P<via>.*) از حساب (?P<sender_id>\d+) به حساب (?P<receiver_id>\d+) ، صاحب سپرده مبدا: (?P<sender_name>.*)'),
    # ],

    'card': [
        re.compile('انتقال از کارت (?P<sender_id>\d+) به کارت (?P<receiver_id>\d+) با شماره بازیابی (?P<bank_transaction_id>\d+) از ترمینال (?P<terminal>.*) از کانال (?P<via>.*) با شماره پیگیری (?P<tracking_id>\d+)'),
    ],
}


@dataclasses.dataclass
class TransactionDescriptionInfo:
    bank_transaction_id: str
    record_type: str
    sender_identifier: str
    receiver_identifier: str


def parse_parsian_description(text: str) -> TransactionDescriptionInfo:
    text = clean_persian_word(text.strip())

    for record_type, patterns in PARSIAN_PATTERNS.items():
        for pattern in patterns:
            groups = pattern.match(text)
            if not groups:
                continue

            if groups:
                data = groups.groupdict()

                return TransactionDescriptionInfo(
                    record_type=record_type,
                    sender_identifier=data['sender_id'],
                    receiver_identifier=data['receiver_id'],
                    bank_transaction_id=data['bank_transaction_id'],
                )
    else:
        raise ParseError
