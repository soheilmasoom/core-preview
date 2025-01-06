import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.models import SystemConfig
from accounts.utils.telegram import send_system_message
from accounts.verifiers.utils import ServerError
from financial.exceptions import NoChannelError
from financial.interface.base_interface import WithdrawRefundedDTO
from financial.models import Gateway, Payment, FiatWithdrawRequest, BankAccount, PaymentIdGateway, PaymentId
from financial.payment_id import get_payment_id_client
from financial.utils.interface import get_withdraw_channel
from ledger.utils.fields import PENDING, DONE, PROCESS, CANCELED

logger = logging.getLogger(__name__)


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
    for gateway in Gateway.objects.filter(active=True, ipg_deposit_enable=True):
        try:
            channel = get_withdraw_channel(gateway)
            channel.update_missing_payments()
        except NoChannelError:
            pass
        except ServerError as e:
            logger.info(f'Failed to update missing payments due to {e}')


@shared_task(queue='finance')
def handle_missing_payment_ids():
    for payment_id in PaymentId.objects.filter(verified=False, deleted=False):
        client = get_payment_id_client(payment_id.gateway)
        client.check_payment_id_status(payment_id)


@shared_task(queue='finance')
def handle_waiting_payment_ids():
    if not SystemConfig.get_system_config().pay_id_requests_process:
        return

    gateways = PaymentIdGateway.live_objects.all()

    for gateway in gateways:
        client = get_payment_id_client(gateway)
        client.create_payments_requests()


@shared_task(queue='finance')
def check_withdraw_refunds():
    start = timezone.now().astimezone() - timedelta(days=7)

    gateway_ids = list(FiatWithdrawRequest.objects.filter(
        created__gte=start,
        status=DONE
    ).values_list('gateway_id', flat=True).distinct())

    if not gateway_ids:
        return

    for gateway in Gateway.objects.filter(id__in=gateway_ids):
        channel = get_withdraw_channel(gateway)
        refunds = channel.get_refunded_withdraws(start=start)
        refunds_map = {r.id: r for r in refunds}

        withdraws = FiatWithdrawRequest.objects.filter(
            id__in=list(refunds_map.keys()),
            status__in=(PROCESS, PENDING, DONE),
            gateway=gateway
        )

        for withdraw in withdraws:
            refund = refunds_map[withdraw.id]  # type: WithdrawRefundedDTO

            assert withdraw.amount == refund.amount
            assert withdraw.ref_id == refund.ref_id

            with transaction.atomic():
                # reject bank account on withdraw refund
                withdraw.bank_account.reject(reason=BankAccount.TRANSACTION_REFUND)

                if withdraw.status == DONE:
                    refund_done = withdraw.refund()
                    action_name = 'refunded'
                else:
                    refund_done = withdraw.change_status(CANCELED)
                    action_name = 'canceled'

                if refund_done:
                    withdraw.add_comment(f'{action_name.capitalize()} due to gateway cancel')

                    send_system_message(
                        message=f'Withdraw {withdraw.id} {action_name} due to gateway cancel',
                        link=url_to_edit_object(withdraw),
                    )
