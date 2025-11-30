from django.db import models

from financial.validators import iban_validator


class GeneralBankAccount(models.Model):
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

    def __str__(self):
        return self.iban
