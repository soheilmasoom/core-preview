from financial.models import Gateway, PayIdGateway
from financial.utils.payment_id_client import get_payment_id_clients


def fix_payment_ids():
    gateway = PayIdGateway.get_active_pay_id()

    if not gateway:
        return

    client = get_payment_id_clients(gateway).first()
    client.create_missing_payment_requests_from_list()
