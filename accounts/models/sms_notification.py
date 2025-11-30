import logging

from django.db import models

from ledger.utils.fields import get_group_id_field

logger = logging.getLogger(__name__)


class SmsNotification(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    recipient = models.ForeignKey(to='accounts.User', on_delete=models.CASCADE)

    content = models.TextField(blank=True)
    sent = models.BooleanField(default=False, db_index=True)

    group_id = get_group_id_field(null=True, db_index=True, default=None)

    class Meta:
        ordering = ('-created', )
        unique_together = ('recipient', 'group_id')
