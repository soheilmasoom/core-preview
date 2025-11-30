import uuid

from django.db import models

from ledger.models import Wallet
from ledger.utils.fields import get_group_id_field, get_amount_field
from stake.models import StakeRequest


class StakeRevenue(models.Model):
    created = models.DateField(db_index=True)

    stake_request = models.ForeignKey(StakeRequest, on_delete=models.CASCADE)

    group_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
    )

    revenue = get_amount_field()

    wallet_source = models.CharField(max_length=8, choices=((Wallet.SPOT, Wallet.SPOT), (Wallet.STAKE, Wallet.STAKE)))

    class Meta:
        unique_together = ('created', 'stake_request')
