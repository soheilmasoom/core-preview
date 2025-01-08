import logging

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId
from financial.models.fast_payment_gateway import FastPaymentGateway

logger = logging.getLogger(__name__)


class BaseClient:
    def __init__(self, gateway: FastPaymentGateway):
        self.gateway = gateway

    def get_token(self):
        raise NotImplementedError

    def get_banks(self):
        raise NotImplementedError

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        raise NotImplementedError

    def create_payment_request(self, external_ref: str) -> PaymentIdRequest:
        raise NotImplementedError

    def check_payment_id_status(self, payment_id: PaymentId):
        raise NotImplementedError

    def create_payments_requests(self):
        raise NotImplementedError
