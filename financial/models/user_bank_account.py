from django.db import models
from django.db.models import UniqueConstraint, Q
from simple_history.models import HistoricalRecords

from financial.models.base_bank_entity import BaseBankEntity
from financial.utils.bank import get_bank_from_iban
from ledger.utils.fields import get_iban_field


class BankAccount(BaseBankEntity):
    history = HistoricalRecords()

    ACTIVE, DEPOSITABLE_SUSPENDED, NON_DEPOSITABLE_SUSPENDED, STAGNANT, UNKNOWN = 'active', 'suspend', 'nsuspend', 'stagnant', 'unknown'

    iban = get_iban_field()

    bank = models.CharField(max_length=256, blank=True)
    deposit_address = models.CharField(max_length=64, blank=True)
    card_pan = models.CharField(max_length=20, blank=True)

    deposit_status = models.CharField(
        max_length=8,
        blank=True,
        choices=(
            (ACTIVE, 'active'), (DEPOSITABLE_SUSPENDED, 'suspend'), (NON_DEPOSITABLE_SUSPENDED, 'nodep suspend'),
            (STAGNANT, 'stagnant')
        )
    )

    owners = models.JSONField(blank=True, null=True)

    stake_holder = models.BooleanField(default=False)

    def __str__(self):
        return self.iban[:6] + '********' + self.iban[-5:] + ' ' + self.bank

    def save(self, *args, **kwargs):
        if not self.id:
            bank = get_bank_from_iban(self.iban)
            if bank:
                self.bank = bank.slug

        super(BankAccount, self).save(*args, **kwargs)

    class Meta:
        verbose_name = 'حساب بانکی'
        verbose_name_plural = 'حساب‌های بانکی'

        constraints = [
            UniqueConstraint(
                fields=["iban", "user"],
                name="unique_bank_account_iban",
                condition=Q(deleted=False),
            ),
            UniqueConstraint(
                fields=["iban"],
                name="unique_bank_account_verified_iban",
                condition=Q(verified=True, deleted=False),
            )
        ]

        permissions = [
            ("list_bankaccount", "Can list bank account"),
        ]

