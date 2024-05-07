from django.db import models
from django.db.models import UniqueConstraint, Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from simple_history.models import HistoricalRecords

from financial.utils.bank import get_bank_from_iban, get_bank_from_card_pan
from financial.validators import iban_validator, bank_card_pan_validator


class LiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted=False)


class BankCard(models.Model):
    DUPLICATED = 'duplicated'

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(to='accounts.User', on_delete=models.PROTECT)

    card_pan = models.CharField(
        verbose_name='شماره کارت',
        max_length=20,
        validators=[bank_card_pan_validator],
    )

    verified = models.BooleanField(null=True, blank=True)
    kyc = models.BooleanField(default=False)

    deleted = models.BooleanField(default=False)

    bank = models.CharField(blank=True, max_length=64)
    type = models.CharField(blank=True, max_length=64)
    owner_name = models.CharField(blank=True, max_length=256)
    deposit_number = models.CharField(blank=True, max_length=128)

    reject_reason = models.CharField(max_length=128, blank=True)

    history = HistoricalRecords()

    objects = models.Manager()
    live_objects = LiveManager()

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


class BankAccount(models.Model):
    ACTIVE, DEPOSITABLE_SUSPENDED, NON_DEPOSITABLE_SUSPENDED, STAGNANT, UNKNOWN = 'active', 'suspend', 'nsuspend', 'stagnant', 'unknown'

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(to='accounts.User', on_delete=models.PROTECT)

    iban = models.CharField(
        max_length=26,
        validators=[iban_validator],
        verbose_name='شبا'
    )

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

    verified = models.BooleanField(null=True, blank=True)
    deleted = models.BooleanField(default=False)

    stake_holder = models.BooleanField(default=False)

    history = HistoricalRecords()

    objects = models.Manager()
    live_objects = LiveManager()

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


class BankCardSerializer(serializers.ModelSerializer):
    info = serializers.SerializerMethodField()

    def get_info(self, bank_card: BankCard):
        bank = get_bank_from_card_pan(bank_card.card_pan)
        return bank and bank.as_dict()

    class Meta:
        model = BankCard
        fields = ('id', 'card_pan', 'verified', 'info')
        read_only_fields = ('verified', )

    def create(self, validated_data: dict):
        user = validated_data['user']
        card_pan = validated_data['card_pan']

        if BankCard.live_objects.filter(user=user, card_pan=card_pan).exists():
            raise ValidationError('این شماره کارت قبلا ثبت شده است.')

        bank_card = super().create(validated_data)

        from financial.tasks.verify import verify_bank_card_task
        verify_bank_card_task.delay(bank_card.id)

        return bank_card


class BankAccountSerializer(serializers.ModelSerializer):

    info = serializers.SerializerMethodField()

    def get_info(self, bank_account: BankAccount):
        bank = get_bank_from_iban(bank_account.iban)
        return bank and bank.as_dict()

    class Meta:
        model = BankAccount
        fields = ('id', 'iban', 'verified', 'info')
        read_only_fields = ('verified', )

    def create(self, validated_data: dict):
        user = validated_data['user']
        iban = validated_data['iban']

        if BankAccount.live_objects.filter(user=user, iban=iban).exists():
            raise ValidationError('این شماره شبا قبلا ثبت شده است.')

        old = BankAccount.objects.filter(user=user, iban=iban, deleted=True).order_by('id').last()

        if old:
            old.deleted = False
            old.save(update_fields=['deleted'])
            return old

        bank_account = super().create(validated_data)

        from financial.tasks.verify import verify_bank_account_task
        verify_bank_account_task.delay(bank_account.id)

        return bank_account
