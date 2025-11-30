import logging
from uuid import uuid4

from django.db import models
from django.db.models import CheckConstraint, Q

from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class ReferralTrx(models.Model):

    REFERRER = 'referrer'
    TRADER = 'trader'

    created = models.DateTimeField(auto_now_add=True)

    referral = models.ForeignKey(
        to='accounts.Referral',
        on_delete=models.CASCADE,
    )
    trader = models.ForeignKey(
        to='accounts.Account',
        on_delete=models.CASCADE,
    )

    group_id = models.UUIDField(default=uuid4, db_index=True)

    referrer_amount = get_amount_field()
    trader_amount = get_amount_field()

    class Meta:
        constraints = [
            CheckConstraint(check=Q(referrer_amount__gte=0, trader_amount__gte=0),
                            name='check_market_referraltrx_amounts', ),
        ]
