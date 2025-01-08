import logging

from accounts.models import User
from financial.models import PaymentId, PaymentIdGateway
from financial.fast_payment.base_client import BaseClient

logger = logging.getLogger(__name__)


class MockClient(BaseClient):
    def create_payment_id(self, user: User, full_name: str = '') -> PaymentId:
        destination, _ = PaymentIdGateway.objects.get_or_create(
            iban='IR760120020000008992439961',
            defaults={
                'name': 'ایوان رایان پیام',
                'bank': 'MELLAT',
                'deposit_address': '8992439961'
            }
        )

        pay_id, _ = PaymentId.objects.get_or_create(
            gateway=self.gateway,
            user=user,
            defaults={
                'pay_id': f'1111100000{user.id}',
                'gateway': destination
            }
        )

        return pay_id

    def check_payment_id_status(self, payment_id: PaymentId):
        payment_id.verified = True
        payment_id.save(update_fields=['verified'])
