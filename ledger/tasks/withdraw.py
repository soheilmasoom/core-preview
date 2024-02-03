import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from ledger.models import Transfer
from ledger.utils.fields import PROCESS, PENDING
from ledger.utils.fraud import verify_crypto_withdraw
from ledger.utils.provider import get_provider_requester
from ledger.withdraw.exchange import handle_provider_withdraw, change_to_manual

logger = logging.getLogger(__name__)


@shared_task(queue='transfer')
def create_provider_withdraw(transfer_id: int):
    handle_provider_withdraw(transfer_id)


@shared_task(queue='transfer')
def update_provider_withdraw():
    return

    re_handle_transfers = Transfer.objects.filter(
        deposit=False,
        source=Transfer.PROVIDER,
        status=PROCESS,
    )

    for transfer in re_handle_transfers:
        create_provider_withdraw.delay(transfer.id)

    transfers = Transfer.objects.filter(
        deposit=False,
        source=Transfer.PROVIDER,
        status=PENDING
    )

    for transfer in transfers:
        data = get_provider_requester().get_transfer_status(transfer)

        if not data:
            continue

        status = data.status

        if status == CANCELED:
            change_to_manual(transfer)

        elif status == DONE:
            transfer.accept(data.tx_id)


@shared_task(queue='transfer')
def create_withdraw(transfer_id: int):

    with transaction.atomic():
        transfer = Transfer.objects.select_for_update().get(id=transfer_id)

        if not verify_crypto_withdraw(transfer):
            logger.info('Ignoring cyrpto withdraw due to not verified')
            return

        if transfer.in_freeze_time():
            return

        if transfer.source != Transfer.SELF:
            logger.info('ignored because non self source')
            return

        if transfer.status != PROCESS:
            logger.info('ignored due to invalid status')
            return

        from ledger.requester.withdraw_requester import RequestWithdraw

        asset = transfer.wallet.asset
        coin_mult = asset.get_coin_multiplier()

        assert coin_mult == 1 or (asset.symbol != asset.original_symbol and asset.original_symbol)

        response = RequestWithdraw().withdraw_from_hot_wallet(
            receiver_address=transfer.out_address,
            amount=transfer.amount * coin_mult,
            network=transfer.network.symbol,
            asset=asset.get_original_symbol(),
            transfer_id=transfer.id,
            memo=transfer.memo
        )

        resp_data = response.json()

        if response.ok:
            transfer.status = PENDING
            transfer.save(update_fields=['status'])

        elif response.status_code == 400 and resp_data.get('type') == 'Invalid':
            logger.info('withdraw failed %s %s %s' % (transfer.id, response.status_code, resp_data))

            transfer.reject()

            if resp_data.get('reason') == 'InvalidReceiverAddress':
                user = transfer.wallet.account.user
                from accounts.models import Notification
                Notification.send(
                    recipient=user,
                    title='برداشت ناموفق',
                    level=Notification.ERROR,
                    message='آدرس مقصد وارد شده نامعتبر است'
                )

        elif response.status_code == 400 and resp_data.get('type') == 'NotHandled':
            logger.info('withdraw switch %s %s' % (transfer.id, resp_data))

            # if transfer.network_asset.allow_provider_withdraw:
            #     transfer.source = Transfer.PROVIDER
            #     transfer.save(update_fields=['source'])
            #     create_provider_withdraw(transfer_id=transfer.id)
            # else:
            change_to_manual(transfer)

        else:
            logger.info('withdraw failed %s %s %s' % (transfer.id, response.status_code, resp_data))

            transfer.status = PENDING
            transfer.save(update_fields=['status'])

            logger.warning('Error sending withdraw to blocklink', extra={
                'transfer_id': transfer_id,
                'resp': resp_data
            })


@shared_task(queue='transfer')
def update_withdraws():
    if not verify_crypto_withdraw():
        logger.info('Ignoring cyrpto withdraw due to not verified')
        return

    re_handle_transfers = Transfer.objects.filter(
        deposit=False,
        source=Transfer.SELF,
        status=PROCESS,
        created__lte=timezone.now() - timedelta(seconds=Transfer.FREEZE_SECONDS),
    )

    for transfer in re_handle_transfers:
        create_withdraw.delay(transfer.id)
