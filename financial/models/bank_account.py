import logging

from django.db import models, transaction
from django.db.models import FileField

from financial.exceptions import DuplicatedPaymentError
from financial.parser.base_parser import ParseError
from financial.parser.parsian.statement_parser import parse_parsian_statement
from financial.payment_id import get_payment_id_client
from ledger.utils.fields import get_created_field, get_status_field, CANCELED, PENDING, DONE

logger = logging.getLogger(__name__)


class BankStatement(models.Model):
    created = get_created_field()
    gateway = models.ForeignKey(
        to='PaymentIdGateway',
        on_delete=models.CASCADE,
        limit_choices_to={'can_add_statement': True}
    )

    title = models.CharField(max_length=256)
    file = FileField(upload_to='finance/statements/')
    status = get_status_field()
    message = models.TextField(blank=True)

    def process_file(self):
        if self.status != PENDING:
            return

        statement_client = get_payment_id_client(self.gateway)

        with transaction.atomic():
            try:
                transactions = parse_parsian_statement(self.file.read())

                for t in transactions:
                    try:
                        statement_client.process_new_deposit(t)
                    except DuplicatedPaymentError:
                        logger.info('statement transaction ignored due to duplicated payment')
                        continue

            except ParseError as e:
                self.message = e.args[0]
                self.status = CANCELED
                self.save(update_fields=['message', 'status'])

            # for t in transactions:
            #     BankTransaction.objects.get_or_create(
            #         reference_number=t.reference_number,
            #         defaults={
            #             'gateway': self.gateway,
            #             'deposit_type': t.deposit_type,
            #             'amount': t.amount,
            #             'transaction_date': t.created,
            #             'account_balance': t.balance,
            #             'sender_iban': t.sender_iban,
            #             'sender_account': t.sender_account,
            #             'sender_name': t.sender_name,
            #             'deposit_number': t.deposit_number,
            #             'sender_bank': t.sender_bank,
            #             'tracking_id': t.tracking_id,
            #             'bank_branch': t.bank_branch,
            #             'description': t.description
            #         }
            #     )

            self.status = DONE
            self.save(update_fields=['message', 'status'])

    def __str__(self):
        return self.title
