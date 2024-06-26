from typing import Type

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from accounts.utils.admin import url_to_admin_list
from accounts.utils.telegram import send_system_message
from accounts.utils.validation import timedelta_message
from health.alert import ALERTS
from health.alert.types import Status, BaseAlertHandler
from ledger.utils.fields import get_amount_field
from ledger.utils.precision import humanize_number


class AlertType(models.Model):
    active = models.BooleanField(default=True)

    type = models.CharField(max_length=32, choices=[(t, t) for t in ALERTS])
    warning_threshold = get_amount_field(default=0)
    error_threshold = get_amount_field(default=0)

    alert_on_same_status = models.BooleanField(default=False)

    def get_status(self) -> Status:
        alert_class = ALERTS[self.type]  # type: Type[BaseAlertHandler]
        alert = alert_class(self.warning_threshold, self.error_threshold)
        return alert.get_status()

    def __str__(self):
        return f'{self.type} wt: {humanize_number(self.warning_threshold)}, et: {humanize_number(self.error_threshold)}'

    def check_trigger(self, status: Status):
        last = AlertTrigger.objects.filter(alert_type=self).first()

        if not last or \
                (last.status, last.count, last.description) != (status.type, status.count, status.description):

            new_trigger, _ = AlertTrigger.objects.update_or_create(
                alert_type=self,
                defaults={
                    'last_ok_time': timezone.now() if not last or last.status == Status.OK else last.last_ok_time,
                    'status': status.type,
                    'count': status.count,
                    'description': status.description,
                }
            )

            self.trigger(last, new_trigger)

    def trigger(self, old: 'AlertTrigger', new: 'AlertTrigger'):
        assert self == new.alert_type

        if old:
            assert self == old.alert_type

            if not self.alert_on_same_status and old.status == new.status:
                return

        emojis = {Status.OK: '🟢', Status.WARNING: '🟠', Status.ERROR: '🔴'}

        message = f"{emojis[new.status]} {new.status.upper()}: {self.type.replace('_', ' ').capitalize()}."

        if new.status != Status.OK:
            message += f'\n   More ({new.count}): {new.description}'

        if old and new.status == Status.OK:
            td_message = timedelta_message(timezone.now() - old.last_ok_time, ignore_seconds=True)
            if td_message:
                message += f'\n   It was down for {td_message}.'

        message += '\n'

        send_system_message(
            message, link=url_to_admin_list(self)
        )


class AlertTrigger(models.Model):
    history = HistoricalRecords()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    alert_type = models.OneToOneField(AlertType, on_delete=models.CASCADE)

    last_ok_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=8, default=Status.OK)
    count = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
