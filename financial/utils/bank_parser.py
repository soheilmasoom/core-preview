import dataclasses
import re

from accounts.utils.similarity import clean_persian_word


@dataclasses.dataclass
class TransactionInfo:
    pass


PARSIAN_PATTERNS = [
    # PAYA
    r'(?P<deposit_type>واریز|برداشت) (?P<transfer_type>پایا) با مشخصات : رهگیری: (?P<tracking_id>\d+) شناسه پرداخت: (?P<deposit_number>EMPTY|\d+) شناسه تراکنش: (?P<transaction_id>[0-9a-zA-Z\.-_]+) شرح: (?P<description>[\w-]+) نام: (?P<sender_name>.*) شبا: (?P<sender_iban>IR\d+) - (?P<sender_bank>.*)',

    # POL
    r'تراکنش (?P<transfer_type>پل) به مشخصات با کد رهگیری (?P<tracking_id>\d+)، شناسه پرداخت (?P<deposit_number>EMPTY|\d+)، به نام (?P<sender_name>.*) و شماره شبا (?P<sender_iban>IR\d+) - بانک (?P<sender_bank>.*)',

    # Internal
    'انتقال وجه از طریق (?P<via>.*) از حساب (?P<sender_account>\d+) به حساب (?P<receiver_account>\d+) ، صاحب سپرده مبدا: (?P<sender_name>.*)'
]


def parse_parsian_description(text: str):
    text = clean_persian_word(text.strip())

    paya_pattern = r''

    groups = re.match(paya_pattern, text)

    return groups.groupdict()

