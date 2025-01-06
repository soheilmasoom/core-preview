from django.db import models
from django.db.models import UniqueConstraint, Q
from simple_history.models import HistoricalRecords

from financial.models.base_bank_entity import BaseBankEntity
from financial.utils.bank import get_bank_from_card_pan
from financial.validators import bank_card_pan_validator


class BankCard(BaseBankEntity):
    CREDIT_FAMILY_TYPES = ('ONLINE_PREPAID', 'CREDIT', 'GIFT_CARD', 'VIRTUAL_CARD')
    history = HistoricalRecords()

    card_pan = models.CharField(
        verbose_name='شماره کارت',
        max_length=20,
        validators=[bank_card_pan_validator],
    )

    kyc = models.BooleanField(default=False)

    bank = models.CharField(blank=True, max_length=64)
    type = models.CharField(blank=True, max_length=64)
    owner_name = models.CharField(blank=True, max_length=256)
    deposit_number = models.CharField(blank=True, max_length=128)

    def __str__(self):
        if len(self.card_pan) < 10:
            return self.card_pan

        return self.card_pan[:4] + '********' + self.card_pan[-4:] + ' ' + self.bank

    def save(self, *args, **kwargs):
        if not self.id:
            bank = get_bank_from_card_pan(self.card_pan)
            if bank:
                self.bank = bank.slug

        super(BankCard, self).save(*args, **kwargs)

    class Meta:
        verbose_name = 'کارت بانکی'
        verbose_name_plural = 'کارت‌های بانکی'

        constraints = [
            UniqueConstraint(
                fields=['card_pan', 'user'],
                name='unique_bank_card_card_pan',
                condition=Q(deleted=False),
            ),
            UniqueConstraint(
                fields=['user'],
                name="bank_card_unique_kyc_user",
                condition=Q(deleted=False, kyc=True),
            ),
            UniqueConstraint(
                fields=["card_pan"],
                name="unique_bank_card_verified_card_pan",
                condition=Q(verified=True, deleted=False),
            )
        ]

        permissions = [
            ("list_bankcard", "Can list bank card"),
        ]
