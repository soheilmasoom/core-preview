import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from ledger.models import InternalTransfer
from ledger.utils.fields import PROCESS, PENDING

logger = logging.getLogger(__name__)

@shared_task(queue='internal-transfer')
def update_internal_transfers():
    with transaction.atomic():
        pending_transfers = InternalTransfer.objects.select_for_update().filter(
            status=PENDING,
        )
        for transfer in pending_transfers:
            if transfer.in_freeze_time():
                continue
            try:
                transfer.accept()
                transfer.alert_user()
            except Exception as e:
                logger.error(f"Error processing internal transfer {transfer.id}: {str(e)}")
