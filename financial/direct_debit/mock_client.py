import logging

from accounts.models import User
from financial.direct_debit.base_client import BaseClient
from financial.models.authorization_id import AuthorizationId
from financial.models.direct_debit_bank import DirectDebitBank
from financial.models.direct_debit_request import DirectDebitRequest
from ledger.utils.fields import PROCESS

logger = logging.getLogger(__name__)


class MockVandarClient(BaseClient):
    BASE_URL = 'https://api.vandar.io'
    _token = None

    def get_authorization_create_url(self, user: User, bank: DirectDebitBank):
        auth_token = self.get_authorization_token(user, bank)

        return f'https://subscription.vandar.io/authorizations/{auth_token}'

    def get_authorization_token(self, user: User, bank: DirectDebitBank):
        auth_token = 'test_token'
        auth_id, created = AuthorizationId.objects.get_or_create(user=user, bank=bank, defaults={
            'token': auth_token
        })

        return auth_token

    def accept_authorization_id(self, auth_id: AuthorizationId):
        auth_id.verified = True
        auth_id.save(update_fields=['verified'])

    def cancel_authorization_id(self, auth_id: AuthorizationId):
        auth_id.deleted = True
        auth_id.save(update_fields=['deleted'])

    def create_payment_data(self, auth_id: AuthorizationId, amount):
        fee = 0
        # fee = math.ceil(item['balance'] / 10_000_000) * 250
        payment_request = DirectDebitRequest.objects.create(
            owner=auth_id,
            gateway=self.gateway,
            amount=amount - fee,
            fee=fee,
            status=PROCESS,
        )

        return payment_request.accept()
