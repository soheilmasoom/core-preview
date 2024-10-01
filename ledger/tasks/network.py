from celery import shared_task
from django.db import transaction
from django.utils import timezone

from ledger.models import NetworkSchedule
from ledger.utils.fields import PENDING, DONE


@shared_task(queue='celery')
def check_network_schedules():

    for ns in NetworkSchedule.objects.filter(status=PENDING, disable_at__lte=timezone.now()):
        with transaction.atomic():
            ns.network.can_deposit = False
            ns.network.can_withdraw = False
            ns.network.save(update_fields=['can_deposit', 'can_withdraw'])
            ns.status = DONE
            ns.save(update_fields=['status'])
