from django.db import models

from financial.utils.encryption import decrypt
from financial.utils.manager import LiveManager
from financial.validators import iban_validator


class PayIdGateway(models.Model):
    TYPES = JIBIT_OLD, JIBIT, PARSIAN = \
        'jibit_old', 'jibit', 'parsian'

    type = models.CharField(
        max_length=16,
        choices=[(t, t) for t in TYPES],
        default=JIBIT_OLD,
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

    priority = models.SmallIntegerField(default=1)

    active = models.BooleanField(default=False)
    live_objects = LiveManager()

    def __str__(self):
        return self.iban

    class Meta:
        ordering = ['priority']

    @property
    def payment_id_secret(self):
        return decrypt(self.payment_id_secret_encrypted)
