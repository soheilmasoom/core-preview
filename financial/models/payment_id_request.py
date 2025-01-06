from django.db import models
from django.db.models import Q, CheckConstraint, UniqueConstraint

from financial.models import Payment
from ledger.utils.fields import get_status_field, DONE, get_group_id_field, CANCELED, get_iban_field, PROCESS, \
    INIT
from ledger.utils.precision import humanize_number
from ledger.utils.wallet_pipeline import WalletPipeline


class PaymentIdRequest(models.Model):
    PENDING_STATES = [INIT, PROCESS]

    created = models.DateTimeField(auto_now_add=True)

    owner = models.ForeignKey('PaymentId', on_delete=models.PROTECT, null=True, blank=True)
    status = get_status_field()

    gateway = models.ForeignKey('PaymentIdGateway', on_delete=models.PROTECT)

    amount = models.PositiveBigIntegerField()
    fee = models.PositiveBigIntegerField()
    balance = models.PositiveBigIntegerField(default=0)

    external_ref = models.CharField(max_length=64, blank=True, unique=True)
    bank_ref = models.CharField(max_length=64, blank=True)
    bank_transaction_id = models.CharField(max_length=64, blank=True)

    sender_iban = get_iban_field()
    sender_name = models.CharField(max_length=256, blank=True)
    sender_identifier = models.CharField(max_length=256, blank=True)
    record_type = models.CharField(max_length=256, blank=True)

    kyt_passed = models.BooleanField(null=True, blank=True)
    deposit_time = models.DateTimeField()

    raw_payment_id = models.CharField(max_length=64, blank=True)
    raw_data = models.TextField(blank=True)

    group_id = get_group_id_field(unique=True)
    payment = models.OneToOneField('financial.Payment', null=True, blank=True, on_delete=models.CASCADE)

    comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(status=INIT) | Q(owner__isnull=False),
                name='payment_id_request_owner_null_condition'
            ),
            UniqueConstraint(
                fields=('bank_transaction_id', ),
                condition=~Q(bank_transaction_id=''),
                name='unique_financial_paymentidrequest_bank_transaction_id',
            ),

        ]

    def __str__(self):
        return f'{self.id}- {humanize_number(self.amount)} IRT ({self.status})'

    def accept(self):
        with WalletPipeline() as pipeline:
            req = PaymentIdRequest.objects.select_for_update().get(id=self.id)

            if req.payment or req.status not in self.PENDING_STATES:
                return

            payment_id = req.owner

            req.payment = Payment.objects.create(
                group_id=req.group_id,
                user=payment_id.master or payment_id.user,
                amount=req.amount,
                fee=req.fee,
                source=Payment.PAY_ID,
            )
            req.payment.accept(pipeline, req.bank_ref)

            req.status = DONE
            req.save(update_fields=['status', 'payment'])

    def reject(self):
        PaymentIdRequest.objects.filter(id=self.id, status__in=self.PENDING_STATES).update(status=CANCELED)
