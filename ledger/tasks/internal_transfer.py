import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from ledger.models import InternalTransfer, ManualWithdraw
from ledger.utils.fields import PROCESS, PENDING

logger = logging.getLogger(__name__)

@shared_task(queue='internal-transfer')
def update_internal_transfers():
    current_time = timezone.now()
    freeze_time_threshold = current_time - timedelta(seconds=InternalTransfer.FREEZE_SECONDS)

    with transaction.atomic():
        pending_transfers = InternalTransfer.objects.select_for_update().filter(
            status=PENDING,
            created__lte=freeze_time_threshold
        )
        for transfer in pending_transfers:
            try:
                transfer.accept()
                transfer.alert_user()
            except Exception as e:
                logger.error(f"Error processing internal transfer {transfer.id}: {str(e)}")