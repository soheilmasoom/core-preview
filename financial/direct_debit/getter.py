from typing import Union

from django.conf import settings

from financial.direct_debit import MockVandarClient, BaseClient
from financial.direct_debit.vandar_client import VandarClient
from financial.models.direct_debit_gateway import DirectDebitGateway

_CLIENTS = {
    DirectDebitGateway.VANDAR: VandarClient,
}


def get_direct_debit_client(gateway: DirectDebitGateway) -> Union[BaseClient, None]:
    if settings.DEBUG_OR_TESTING:
        return MockVandarClient(gateway)

    client = _CLIENTS.get(gateway.type, None)

    if client is None:
        return None

    return client(gateway)
