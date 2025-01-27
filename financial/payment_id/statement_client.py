import logging
from decimal import Decimal

from accounts.models import User
from accounts.utils.similarity import name_similarity
from financial.models import PaymentIdRequest, PaymentId, PaymentIdGateway
from financial.parser.base_parser import TransactionInfo
from financial.payment_id import BaseClient
from financial.utils.payment_id import create_or_update_payment_id_request
from ledger.utils.fields import INIT

logger = logging.getLogger(__name__)


class StatementClient(BaseClient):

    def create_payments_requests(self):
        pass

    def process_new_deposit(self, transaction: TransactionInfo) -> 'PaymentIdRequest':
        payment_request = create_or_update_payment_id_request(self.gateway, transaction)
        if payment_request.status != INIT:
            return payment_request

        if transaction.refund_type or transaction.refund_track_id:
            payment_request.change_to_refund()
            payment_request.refresh_from_db()

        elif payment_request.user:
            ignore_kyt = self.gateway.type != PaymentIdGateway.PAYMENT_ID or \
                         payment_request.record_type == PaymentIdRequest.CARD

            user_full_name = payment_request.user.get_full_name()

            if payment_request.kyt_passed or ignore_kyt or name_similarity(payment_request.sender_name, user_full_name):
                payment_request.accept()
                payment_request.refresh_from_db()

        return payment_request

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        pass

    def check_payment_id_status(self, payment_id: PaymentId):
        return True

    def update_payment_request(self, payment_request: PaymentIdRequest) -> PaymentIdRequest:
        pass

    def get_balance(self) -> Decimal:
        return Decimal()

    def refund_payment_request(self, payment_request: PaymentIdRequest) -> bool:
        raise NotImplementedError

    def accept_payment_request(self, payment_request: PaymentIdRequest):
        payment_request.accept()

    def reject_payment_request(self, payment_request: PaymentIdRequest):
        payment_request.change_to_canceled()
