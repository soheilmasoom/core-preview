from typing import Union

from django.conf import settings

from financial.fast_payment import MockClient, BaseClient
from financial.fast_payment.vandar_client import VandarClient
from financial.models.fast_payment_gateway import FastPaymentGateway

_CLIENTS = {
    FastPaymentGateway.VANDAR: VandarClient,
}


def get_fast_payment_client(gateway: FastPaymentGateway) -> Union[BaseClient, None]:
    # if settings.DEBUG_OR_TESTING_OR_STAGING:
    #     return MockClient(gateway)

    client = _CLIENTS.get(gateway.type, None)

    if client is None:
        return None

    return client(gateway)
