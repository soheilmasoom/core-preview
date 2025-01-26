from typing import Union

from financial.models import PaymentIdGateway
from financial.payment_id import MockClient, JibitClient, JibitClientV2, BaseClient, StatementClient

_CLIENTS = {
    PaymentIdGateway.JIBIT_OLD: JibitClient,
    PaymentIdGateway.JIBIT: JibitClientV2,
    PaymentIdGateway.STATEMENT: StatementClient,
    PaymentIdGateway.MOCK: MockClient,
}


def get_payment_id_client(gateway: PaymentIdGateway) -> Union[BaseClient, None]:
    client = _CLIENTS.get(gateway.channel, None)

    if client:
        return client(gateway)
