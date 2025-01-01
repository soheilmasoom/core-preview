import dataclasses
from datetime import datetime


@dataclasses.dataclass
class TransactionInfo:
    created: datetime
    deposit_type: str
    amount: int
    reference_number: str
    balance: int
    deposit_number: str = ''
    sender_iban: str = ''
    sender_account: str = ''
    sender_name: str = ''
    sender_bank: str = ''
    tracking_id: str = ''
    bank_branch: str = ''
    description: str = ''


class ParseError(Exception):
    pass
