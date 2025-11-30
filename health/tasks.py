from celery import shared_task

from health.models import AlertType


@shared_task(queue='alert')
def check_alerts():
    for alert in AlertType.objects.filter(active=True):
        alert.check_trigger(alert.get_status())
