from django.core.validators import validate_integer
from django.db import models
from django.db.models import UniqueConstraint, Q, CheckConstraint

from financial.models import Payment
from ledger.utils.fields import get_status_field, DONE, get_group_id_field, CANCELED, get_iban_field, PROCESS, \
    INIT
from ledger.utils.wallet_pipeline import WalletPipeline


class PaymentId(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    master = models.ForeignKey(
        to='accounts.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='+'
    )
    pay_id = models.CharField(max_length=32, validators=[validate_integer])
    verified = models.BooleanField(default=False)

    gateway = models.ForeignKey('financial.PaymentIdGateway', on_delete=models.PROTECT)

    group_id = get_group_id_field()

    provider_status = models.CharField(max_length=256, blank=True)
    provider_reason = models.CharField(max_length=256, blank=True)

    full_name = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return self.pay_id

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=('user', 'gateway'),
                condition=Q(deleted=False),
                name='unique_financial_paymentid_user_gateway',
            ),
            UniqueConstraint(
                fields=('pay_id', 'gateway'),
                condition=Q(deleted=False),
                name='unique_financial_paymentid_pay_id_gateway',
            ),
        ]


class PaymentIdRequest(models.Model):
    PENDING_STATES = [INIT, PROCESS]

    created = models.DateTimeField(auto_now_add=True)

    owner = models.ForeignKey(PaymentId, on_delete=models.PROTECT, null=True, blank=True)
    status = get_status_field()

    amount = models.PositiveBigIntegerField()
    fee = models.PositiveBigIntegerField()

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
        ]

    def __str__(self):
        return '%s ref=%s' % (self.amount, self.bank_ref)

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
