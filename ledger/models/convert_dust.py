import logging
from datetime import timedelta
from uuid import uuid4

from django.db import models
from django.utils import timezone

from accounts.models import SystemConfig
from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class ConvertDust(models.Model):
    created = models.DateTimeField()
    account = models.ForeignKey('accounts.Account', on_delete=models.CASCADE)
    converted_amount = get_amount_field(default=0)
    base_asset = models.ForeignKey('Asset', on_delete=models.CASCADE)
    group_id = models.UUIDField(default=uuid4, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['account', 'created'], name="ledger_dust_acc_created_idx")
        ]

    @classmethod
    def has_recent_conversion(cls, account):
        in_last_hours: int = SystemConfig.get_system_config().convert_dust_retry_hours_limit
        return ConvertDust.objects.filter(
                account=account,
                created__gte=timezone.now() - timedelta(hours=in_last_hours)
            ).exists()
