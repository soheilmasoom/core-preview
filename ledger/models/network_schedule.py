from django.db import models

from ledger.models import Network
from ledger.utils.fields import get_created_field, get_status_field, PENDING


class NetworkSchedule(models.Model):
    created = get_created_field()

    network = models.ForeignKey(Network, on_delete=models.CASCADE)
    disable_at = models.DateTimeField()

    status = get_status_field(default=PENDING)

    def __str__(self):
        return f'{self.network} @ {self.disable_at}'
