import logging

from django.db import models
from django.db.models import CheckConstraint, Q
from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class ConvertDustTrx(models.Model):
    convert_dust = models.ForeignKey('ledger.ConvertDust', on_delete=models.CASCADE, related_name='convert_dust_trx')
    asset = models.ForeignKey('Asset', on_delete=models.CASCADE)
    base_asset = models.ForeignKey('Asset', on_delete=models.CASCADE, related_name='dust_asset')
    amount = get_amount_field()
    converted_amount = get_amount_field()

    class Meta:
        unique_together = ('convert_dust', 'asset')
        constraints = [
            CheckConstraint(check=Q(converted_amount__gt=0), name='check_ledger_dust_trx_amount', ),
        ]

    def save(self, *args, **kwargs):
        assert self.amount > 0
        assert self.converted_amount > 0

        return super(ConvertDustTrx, self).save(*args, **kwargs)

