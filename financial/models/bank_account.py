from django.db import models

from ledger.utils.fields import get_iban_field, get_bank_field, get_created_field


class Account(models.Model):
    title = models.CharField(max_length=256)

    name = models.CharField(max_length=256)
    bank = get_bank_field()
    iban = get_iban_field(unique=True, blank=True)
    account_number = models.CharField(max_length=64, blank=True)


class BankTransaction(models.Model):
    created = get_created_field()
    account = models.ForeignKey('Account', on_delete=models.CASCADE)

    amount = models.PositiveBigIntegerField()
    transaction_date = models.DateTimeField()

    account_balance = models.PositiveBigIntegerField()

    sender_iban = get_iban_field(blank=True)
    sender_name = models.CharField(max_length=256)
    sender_deposit_number = models.CharField(max_length=256)
    sender_bank = get_bank_field(blank=True)

    reference_number = models.CharField(max_length=64)
    tracking_id = models.CharField(max_length=64)

    bank_branch = models.CharField(max_length=256)

    description = models.TextField()


class BankStatement(models.Model):
    created = get_created_field()
    account = models.ForeignKey('Account', on_delete=models.CASCADE)

