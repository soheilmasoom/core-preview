import dataclasses
from datetime import datetime


@dataclasses.dataclass
class TransactionInfo:
    DEPOSIT, WITHDRAW = 'd', 'w'

    reference_number: str
    account_iban: str
    bank_reference_number: str
    bank_transaction_id: str
    created: datetime
    deposit_type: str
    amount: int
    balance: int
    sender_iban: str
    receiver_iban: str
    record_type: str
    kyt_passed: bool
    deposit_number: str = ''
    sender_identifier: str = ''
    sender_name: str = ''
    raw_data: str = ''


class ParseError(Exception):
    pass
