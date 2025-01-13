import logging
import math
import uuid

import jdatetime
from decouple import config

from accounts.models import User
from financial.models import PaymentIdRequest, PaymentId
from financial.payment_id import BaseClient
from ledger.utils.fields import PROCESS, PENDING, CANCELED

logger = logging.getLogger(__name__)


class ManualClient(BaseClient):

    def create_payments_requests(self):
        pass

    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        existing = PaymentId.objects.filter(user=user, gateway=self.gateway, deleted=False).first()
        if existing:
            return existing

        payment_id = PaymentId.objects.create(
            user=user,
            pay_id=user.national_code,
            verified=True,
            gateway=self.gateway,
        )

        return payment_id

    def check_payment_id_status(self, payment_id: PaymentId):
        return True
