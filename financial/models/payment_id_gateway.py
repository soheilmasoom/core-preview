from django.db import models

from financial.utils.encryption import decrypt
from financial.utils.manager import ActiveManager
from ledger.utils.fields import get_iban_field, get_bank_field


class PaymentIdGateway(models.Model):
    CHANNELS = JIBIT_OLD, JIBIT, MANUAL = 'jibit_old', 'jibit', 'manual'
    TYPES = PAYMENT_ID, POL, CARD = 'paymentId', 'pol', 'card'

    created = models.DateTimeField(auto_now_add=True)

    title = models.CharField(max_length=16)

    type = models.CharField(
        max_length=16,
        choices=[(PAYMENT_ID, 'شناسه واریز'), (POL, 'پل'), (CARD, 'کارت به کارت')],
        default=PAYMENT_ID,
    )

    channel = models.CharField(
        max_length=16,
        choices=[(c, c) for c in CHANNELS],
        default=JIBIT_OLD,
    )

    iban = get_iban_field(unique=True)
    card_pan = models.CharField(max_length=20, blank=True)

    name = models.CharField(max_length=256, blank=True, verbose_name='نام صاحب حساب',)

    bank = get_bank_field()
    deposit_address = models.CharField(max_length=64, blank=True, verbose_name='شماره حساب')

    payment_id_api_key = models.CharField(max_length=1024, blank=True)
    payment_id_secret_encrypted = models.CharField(max_length=4096, blank=True)

    ordering = models.SmallIntegerField(default=0)

    active = models.BooleanField(default=False)
    hide = models.BooleanField(default=False)

    objects = models.Manager()
    live_objects = ActiveManager()

    can_add_statement = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('ordering', 'id')

    @property
    def payment_id_secret(self):
        return decrypt(self.payment_id_secret_encrypted)
