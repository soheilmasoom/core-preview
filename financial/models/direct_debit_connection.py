from django.core.validators import validate_integer
from django.db import models
from django.db.models import UniqueConstraint, Q

from financial.utils.encryption import decrypt, encrypt


class DirectDebitConnection(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)

    auth_id_encrypted = models.CharField(max_length=32, blank=True, validators=[validate_integer])
    verified = models.BooleanField(default=False)

    bank = models.ForeignKey('financial.DirectDebitBank', on_delete=models.CASCADE)

    token = models.CharField(max_length=255, )

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
                fields=('auth_id_encrypted', 'bank'),
                condition=Q(deleted=False),
                name='unique_financial_authorization_id_bank',
            ),
        ]

    @property
    def auth_id(self):
        return decrypt(self.auth_id_encrypted)

    def set_auth_id(self, auth_id: str):
        self.auth_id_encrypted = encrypt(auth_id.strip())
        self.save(update_fields=['auth_id_encrypted'])
