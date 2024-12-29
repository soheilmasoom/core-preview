from django.db import models

from financial.utils.encryption import decrypt
from financial.validators import iban_validator


class PayIdGateway(models.Model):
    TYPES = JIBIT, PARSIAN = \
        'jibit', 'jibimo'

    type = models.CharField(
        max_length=8,
        choices=[(t, t) for t in TYPES],
        default=JIBIT,
    )

    created = models.DateTimeField(auto_now_add=True)

    iban = models.CharField(
        max_length=26,
        validators=[iban_validator],
        verbose_name='شبا',
        unique=True
    )

    name = models.CharField(max_length=256, blank=True)

    bank = models.CharField(max_length=256, blank=True)
    deposit_address = models.CharField(max_length=64, blank=True)

    payment_id_api_key = models.CharField(max_length=1024, blank=True)
    payment_id_secret_encrypted = models.CharField(max_length=4096, blank=True)

    deposit_priority = models.SmallIntegerField(default=1)
    withdraw_priority = models.SmallIntegerField(default=1)

    active = models.BooleanField(default=False)

    def __str__(self):
        return self.iban

    @property
    def payment_id_secret(self):
        return decrypt(self.payment_id_secret_encrypted)

    @classmethod
    def get_active_pay_id_deposit(cls) -> 'PayIdGateway':
        return PayIdGateway.objects.filter(active=True).exclude(payment_id_api_key='').order_by(
            'deposit_priority').first()
