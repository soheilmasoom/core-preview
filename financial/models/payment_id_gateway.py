from django.db import models

from financial.utils.encryption import decrypt
from financial.utils.manager import ActiveManager
from ledger.utils.fields import get_iban_field


class PaymentIdGateway(models.Model):
    TYPES = JIBIT_OLD, JIBIT, MANUAL = \
        'jibit_old', 'jibit', 'manual'

    title = models.CharField(max_length=16)

    type = models.CharField(
        max_length=16,
        choices=[(t, t) for t in TYPES],
        default=JIBIT_OLD,
    )

    created = models.DateTimeField(auto_now_add=True)

    iban = get_iban_field(unique=True)

    name = models.CharField(max_length=256, blank=True, verbose_name='نام صاحب حساب',)

    bank = models.CharField(max_length=256, blank=True)
    deposit_address = models.CharField(max_length=64, blank=True, verbose_name='شماره حساب')

    payment_id_api_key = models.CharField(max_length=1024, blank=True)
    payment_id_secret_encrypted = models.CharField(max_length=4096, blank=True)

    priority = models.SmallIntegerField(default=0)

    active = models.BooleanField(default=False)

    objects = models.Manager()
    live_objects = ActiveManager()

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('priority', )

    @property
    def payment_id_secret(self):
        return decrypt(self.payment_id_secret_encrypted)
