from django.core.validators import validate_integer
from django.db import models
from django.db.models import UniqueConstraint, Q

from ledger.utils.fields import get_group_id_field


class AuthorizationId(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)

    auth_id = models.CharField(max_length=32, blank=True, validators=[validate_integer])
    verified = models.BooleanField(default=False)

    bank = models.ForeignKey('financial.DirectDebitBank', on_delete=models.CASCADE)

    token = models.CharField(max_length=255,)

    # gateway = models.ForeignKey('financial.FastPaymentGateway', on_delete=models.CASCADE) # this to think
    # bank_code = models.CharField(max_length=50, verbose_name="کد") # this to think
    # bank_name = models.CharField(blank=True, null=True, max_length=255, verbose_name="نام") # this to think

    # group_id = get_group_id_field(unique=True)

    def __str__(self):
        return self.auth_id

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=('user', 'bank'),
                condition=Q(deleted=False),
                name='unique_financial_paymentid_user_bank',
            ),
            UniqueConstraint(
                fields=('auth_id', 'bank'),
                condition=Q(deleted=False),
                name='unique_financial_authorization_id_bank',
            ),
        ]
