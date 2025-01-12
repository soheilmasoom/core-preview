import logging

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId
from financial.models.direct_debit_connection import DirectDebitConnection
from financial.models.direct_debit_bank import DirectDebitBank
from financial.models.direct_debit_gateway import DirectDebitGateway

logger = logging.getLogger(__name__)


class BaseClient:
    def __init__(self, gateway: DirectDebitGateway):
        self.gateway = gateway

    def get_token(self):
        raise NotImplementedError

    def get_banks(self):
        raise NotImplementedError

    def get_authorization_create_url(self, user: User, bank: DirectDebitBank):
        raise NotImplementedError

    def get_authorization_token(self, user: User, bank: DirectDebitBank):
        raise NotImplementedError

    def accept_authorization_id(self, authorization_id: DirectDebitConnection):
        raise NotImplementedError

    def cancel_authorization_id(self, authorization_id: DirectDebitConnection):
        raise NotImplementedError

    def create_payment_data(self, auth_id: DirectDebitConnection, amount):
        raise NotImplementedError

    def update_banks(self):
        raise NotImplementedError