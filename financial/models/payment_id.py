from django.core.validators import validate_integer
from django.db import models
from django.db.models import UniqueConstraint, Q

from ledger.utils.fields import get_group_id_field


class PaymentId(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    master = models.ForeignKey(
        to='accounts.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='+'
    )
    pay_id = models.CharField(max_length=32, validators=[validate_integer])
    verified = models.BooleanField(default=False)

    gateway = models.ForeignKey('financial.PaymentIdGateway', on_delete=models.PROTECT)

    group_id = get_group_id_field(unique=True)

    provider_status = models.CharField(max_length=256, blank=True)
    provider_reason = models.CharField(max_length=256, blank=True)

    full_name = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return self.pay_id

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=('user', 'gateway'),
                condition=Q(deleted=False),
                name='unique_financial_paymentid_user_gateway',
            ),
            UniqueConstraint(
                fields=('pay_id', 'gateway'),
                condition=Q(deleted=False),
                name='unique_financial_paymentid_pay_id_gateway',
            ),
        ]
