from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from stake.models import StakeRequest


@shared_task(queue='celery')
def handle_stake_requests_status():
    now = timezone.now()

    to_start_stake_requests = StakeRequest.objects.filter(
        status=StakeRequest.PROCESS,
        created__lte=now - timedelta(days=3) + timedelta(hours=1)
    )
    for stake_request in to_start_stake_requests:
        stake_request.change_status(StakeRequest.DONE)

    to_finish_stake_requests = StakeRequest.objects.filter(
        status=StakeRequest.DONE,
        created__lte=now - timedelta(days=90)
    )

    for stake_request in to_finish_stake_requests:
        stake_request.change_status(StakeRequest.FINISHED)

    to_cancel_stake_requests = StakeRequest.objects.filter(
        status=StakeRequest.CANCEL_PROCESS,
        cancel_request_at__lte=now - timedelta(days=3) + timedelta(hours=1)
    )

    for stake_request in to_cancel_stake_requests:
        stake_request.change_status(StakeRequest.CANCEL_COMPLETE)
