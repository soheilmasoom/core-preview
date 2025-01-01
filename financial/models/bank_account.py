from django.db import models, transaction
from django.db.models import FileField

from financial.parser.base_parser import ParseError
from financial.parser.parsian.statement_parser import parse_parsian_statement
from ledger.utils.fields import get_iban_field, get_bank_field, get_created_field, get_status_field, CANCELED, PENDING, \
    DONE


class Account(models.Model):
    title = models.CharField(max_length=256)

    name = models.CharField(max_length=256)
    bank = get_bank_field()
    iban = get_iban_field(unique=True, blank=True)
    account_number = models.CharField(max_length=64, blank=True)

    can_add_statement = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class BankTransaction(models.Model):
    DEPOSIT_TYPES = DEPOSIT, WITHDRAW = 'd', 'w'

    created = get_created_field()
    account = models.ForeignKey('Account', on_delete=models.CASCADE)

    status = get_status_field()

    deposit_type = models.CharField(
        max_length=1,
        choices=[(DEPOSIT, 'deposit'), (WITHDRAW, 'withdraw')],
        db_index=True
    )

    amount = models.PositiveBigIntegerField()
    transaction_date = models.DateTimeField()

    account_balance = models.PositiveBigIntegerField()

    sender_iban = get_iban_field(blank=True)
    sender_account = models.CharField(max_length=256, blank=True)
    sender_name = models.CharField(max_length=256, blank=True)
    deposit_number = models.CharField(max_length=256, blank=True)
    sender_bank = models.CharField(max_length=256, blank=True)

    reference_number = models.CharField(max_length=64, unique=True)
    tracking_id = models.CharField(max_length=64)

    bank_branch = models.CharField(max_length=256, blank=True)

    description = models.TextField()

    # def accept(self) -> bool:
    #     if self.status != PENDING:
    #         return False
    #
    #     if not self.sender_iban or not self.deposit_number:
    #         return False
    #
    #
    #
    #     with transaction.atomic():
    #


class BankStatement(models.Model):
    created = get_created_field()
    account = models.ForeignKey('Account', on_delete=models.CASCADE, limit_choices_to={'can_add_statement': True})

    title = models.CharField(max_length=256)
    file = FileField(upload_to='finance/statements/')
    status = get_status_field()
    message = models.TextField(blank=True)

    def process_file(self):
        if self.status != PENDING:
            return

        with transaction.atomic():
            try:
                transactions = parse_parsian_statement(self.file.read())
            except ParseError as e:
                self.message = e.args[0]
                self.status = CANCELED
                self.save(update_fields=['message', 'status'])

            for t in transactions:
                BankTransaction.objects.get_or_create(
                    reference_number=t.reference_number,
                    defaults={
                        'account': self.account,
                        'deposit_type': t.deposit_type,
                        'amount': t.amount,
                        'transaction_date': t.created,
                        'account_balance': t.balance,
                        'sender_iban': t.sender_iban,
                        'sender_account': t.sender_account,
                        'sender_name': t.sender_name,
                        'deposit_number': t.deposit_number,
                        'sender_bank': t.sender_bank,
                        'tracking_id': t.tracking_id,
                        'bank_branch': t.bank_branch,
                        'description': t.description
                    }
                )

            self.status = DONE
            self.save(update_fields=['message', 'status'])

    def __str__(self):
        return self.title
