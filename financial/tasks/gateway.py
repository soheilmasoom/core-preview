from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from financial.models import Gateway, Payment, PaymentId
from financial.utils.payment_id_client import get_payment_id_client
from financial.utils.withdraw import FiatWithdraw, NoChannelError
from ledger.utils.fields import PENDING


@shared_task(queue='finance')
def handle_missing_payments():
    # update pending payments
    now = timezone.now()

    pending_payments = Payment.objects.filter(
        status=PENDING,
        paymentrequest__isnull=False,
        created__lte=now - timedelta(minutes=2)
    )

    for payment in pending_payments:
        payment.paymentrequest.get_gateway().verify(payment)

    # update missing payments
    for gateway in Gateway.objects.filter(Q(active=True) | Q(active_for_trusted=True), ipg_deposit_enable=True):
        try:
            channel = FiatWithdraw.get_withdraw_channel(gateway)
            channel.update_missing_payments(gateway)
        except NoChannelError:
            pass


@shared_task(queue='finance')
def handle_missing_payment_ids():
    gateway = Gateway.get_active_pay_id_deposit()

    if not gateway:
        return

    client = get_payment_id_client(gateway)
    client.create_missing_payment_requests()

    for payment_id in PaymentId.objects.filter(verified=False, deleted=False):
        client = get_payment_id_client(payment_id.gateway)
        client.check_payment_id_status(payment_id)
