from django.db import models
from django.db.models import Q, CheckConstraint, UniqueConstraint
from django.utils import timezone

from financial.models import Payment
from ledger.utils.fields import get_status_field, DONE, get_group_id_field, CANCELED, get_iban_field, INIT, REFUND
from ledger.utils.precision import humanize_number
from ledger.utils.wallet_pipeline import WalletPipeline


class PaymentIdRequest(models.Model):
    # ach: paya, rtgs: satna
    RECORD_TYPES = ACH, CARD, INTERNAL, RTGS, POL = 'ach', 'card', 'internal', 'rtgs', 'pol'

    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
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
    record_type = models.CharField(max_length=256, blank=True, choices=[(t, t) for t in RECORD_TYPES])

    kyt_passed = models.BooleanField(null=True, blank=True)
    deposit_time = models.DateTimeField(db_index=True)

    raw_payment_id = models.CharField(max_length=64, blank=True)
    raw_data = models.TextField(blank=True)

    refund_type = models.CharField(max_length=64, blank=True)
    refund_track_id = models.CharField(max_length=64, blank=True)

    group_id = get_group_id_field(unique=True)
    payment = models.OneToOneField('financial.Payment', null=True, blank=True, on_delete=models.SET_NULL)

    comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(status__in=[INIT, CANCELED, REFUND]) | Q(user__isnull=False),
                name='payment_id_request_owner_null_condition'
            ),
            UniqueConstraint(
                fields=('bank_transaction_id', ),
                condition=~Q(bank_transaction_id=''),
                name='unique_financial_paymentidrequest_bank_transaction_id',
            ),

        ]

    def __str__(self):
        return f'{self.status} {humanize_number(self.amount)} IRT'

    def accept(self):
        with WalletPipeline() as pipeline:
            req = PaymentIdRequest.objects.select_for_update().get(id=self.id)  # type: PaymentIdRequest

            if not req.user or req.payment or req.status != INIT:
                return

            req.payment = Payment.objects.create(
                group_id=req.group_id,
                user=req.user,
                amount=req.amount,
                fee=req.fee,
                source=Payment.PAY_ID,
            )
            req.payment.accept(pipeline, req.bank_ref)

            req.status = DONE
            req.save(update_fields=['status', 'payment'])

    def change_to_canceled(self):
        PaymentIdRequest.objects.filter(id=self.id, status=INIT).update(status=CANCELED)

    def change_to_refund(self):
        PaymentIdRequest.objects.filter(id=self.id, status__in=[INIT, CANCELED]).update(status=REFUND)

    def add_comment(self, s: str):
        if not s:
            return

        s = timezone.now().astimezone().strftime('%Y-%m-%d %H:%M:%S') + ' > ' + s

        if self.comment:
            self.comment += '\n' + s
        else:
            self.comment = s

        self.save(update_fields=['comment'])
