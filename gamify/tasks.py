from celery import shared_task
from django.utils import timezone

from gamify.models import MissionTemplate


@shared_task(queue='celery')
def deactivate_expired_missions():
    now = timezone.now()

    MissionTemplate.objects.filter(expiration__lte=now).update(active=False)
