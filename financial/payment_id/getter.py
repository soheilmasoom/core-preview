from typing import Union

from django.conf import settings

from financial.models import PaymentIdGateway
from financial.payment_id import MockClient, JibitClient, JibitClientV2, BaseClient, ManualClient

_CLIENTS = {
    PaymentIdGateway.JIBIT_OLD: JibitClient,
    PaymentIdGateway.JIBIT: JibitClientV2,
    PaymentIdGateway.MANUAL: ManualClient
}


def get_payment_id_client(gateway: PaymentIdGateway) -> Union[BaseClient, None]:
    if settings.DEBUG_OR_TESTING_OR_STAGING:
        return MockClient(gateway)

    client = _CLIENTS.get(gateway.channel, None)
    if client is None:
        return None

    return client(gateway)
