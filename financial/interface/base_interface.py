import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Union

from financial.models import Gateway
from financial.models.withdraw_request import BaseTransfer

logger = logging.getLogger(__name__)


@dataclass
class WalletDTO:
    balance: int
    free: int


@dataclass
class WithdrawDTO:
    tracking_id: str
    status: str
    receive_datetime: Union[datetime, None] = None
    message: str = ''


class BaseChannel:
    def __init__(self, gateway: Gateway, verbose: bool = False):
        self.gateway = gateway
        self.verbose = verbose

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        raise NotImplementedError

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        raise NotImplementedError

    def get_wallet_data(self) -> WalletDTO:
        raise NotImplementedError

    def update_missing_payments(self):
        pass

    def get_instant_banks(self):
        pass

    def is_active(self):
        return bool(self.gateway.withdraw_api_secret_encrypted)
