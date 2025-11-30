from financial.models import Gateway
from financial.utils.payment_id_client import get_payment_id_client


def fix_payment_ids():
    gateway = Gateway.get_active_pay_id_deposit()

    if not gateway:
        return

    client = get_payment_id_client(gateway)
    client.create_missing_payment_requests_from_list()
