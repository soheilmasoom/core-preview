import logging
from decimal import Decimal
from typing import Union

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId, PaymentIdGateway

logger = logging.getLogger(__name__)


class BaseClient:
    def __init__(self, gateway: PaymentIdGateway):
        self.gateway = gateway

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        raise NotImplementedError

    def create_payment_request(self, external_ref: str) -> PaymentIdRequest:
        raise NotImplementedError

    def check_payment_id_status(self, payment_id: PaymentId):
        raise NotImplementedError

    def create_payments_requests(self):
        pass

    def update_payment_request(self, payment_request: PaymentIdRequest):
        raise NotImplementedError

    def accept_payment_request(self, payment_request: PaymentIdRequest):
        raise NotImplementedError

    def refund_payment_request(self, payment_request: PaymentIdRequest):
        raise NotImplementedError

    def get_payment_id(self, deposit_number: str) -> Union[PaymentId, None]:
        return PaymentId.objects.filter(gateway=self.gateway, pay_id=deposit_number).first()

    def get_balance(self) -> Decimal:
        raise NotImplementedError
