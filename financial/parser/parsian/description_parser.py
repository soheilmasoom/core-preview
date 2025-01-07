import dataclasses
import re

from accounts.utils.similarity import clean_persian_word


PARSIAN_PATTERNS = [
    # PAYA
    re.compile(r'(?P<deposit_type>واریز|برداشت) (?P<transfer_type>پایا) با مشخصات : رهگیری: (?P<tracking_id>\d+) شناسه پرداخت: (?P<deposit_number>EMPTY|\d+) شناسه تراکنش: (?P<transaction_id>[0-9a-zA-Z.-_]+) شرح: (?P<description>[\w-]+) نام: (?P<sender_name>.*) شبا: (?P<sender_iban>IR\d+) - (?P<sender_bank>.*)'),

    # POL
    re.compile(r'تراکنش (?P<transfer_type>پل) به مشخصات با کد رهگیری (?P<tracking_id>\d+)، شناسه پرداخت (?P<deposit_number>EMPTY|\d+)، به نام (?P<sender_name>.*) و شماره شبا (?P<sender_iban>IR\d+) - بانک (?P<sender_bank>.*)'),

    # Internal
    re.compile('انتقال وجه از طریق (?P<via>.*) از حساب (?P<sender_account>\d+) به حساب (?P<receiver_account>\d+) ، صاحب سپرده مبدا: (?P<sender_name>.*)'),
]


def parse_parsian_description(text: str):
    text = clean_persian_word(text.strip())

    for pattern in PARSIAN_PATTERNS:
        groups = pattern.match(text)

        if groups:
            return groups.groupdict()
