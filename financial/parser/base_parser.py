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
    deposit_number: str = ''
    sender_account: str = ''
    sender_name: str = ''
    sender_bank: str = ''
    bank_branch: str = ''
    description: str = ''


class ParseError(Exception):
    pass
