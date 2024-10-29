from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from financial.models import Payment
from ledger.utils.fields import get_group_id_field
from ledger.utils.wallet_pipeline import WalletPipeline


class BankPaymentRequest(models.Model):
    DESTINATION_TYPES = JIBIMO, = 'jibimo',

    created = models.DateTimeField(auto_now_add=True)
    group_id = get_group_id_field()

    destination_type = models.CharField(max_length=16, default=JIBIMO, choices=[(d, d) for d in DESTINATION_TYPES])
    amount = models.PositiveBigIntegerField()
    ref_id = models.CharField(blank=True, max_length=256)

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, null=True, blank=True)
    destination_id = models.PositiveIntegerField(null=True, blank=True)

    description = models.TextField(blank=True)

    payment = models.OneToOneField(Payment, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return '%s %s IRT (%s %s)' % (self.user, self.amount, self.destination_type, self.destination_id)

    class Meta:
        unique_together = ('destination_id', 'destination_type')

    def clean(self):
        if self.payment and not self.destination_id:
            raise ValidationError('destination_id can\'t be null')

        if self.payment and self.user != self.payment.user:
            raise ValidationError('users mismatch')

    def get_fee(self):
        if self.destination_type == self.JIBIMO:
            return int(self.amount * Decimal('0.000545'))

    def create_payment(self):
        assert self.user and self.destination_id and self.ref_id

        if self.payment:
            return self.payment

        fee = self.get_fee()

        with WalletPipeline() as pipeline:
            self.payment = Payment.objects.create(
                group_id=self.group_id,
                user=self.user,
                amount=self.amount - fee,
                fee=fee,
                description=self.description[:Payment.DESCRIPTION_SIZE],
                source=Payment.MANUAL,
            )

            self.payment.accept(pipeline, self.ref_id)
            self.save(update_fields=['payment'])


class BankPaymentRequestReceipt(models.Model):
    receipt = models.FileField()
    payment_request = models.ForeignKey(BankPaymentRequest, on_delete=models.CASCADE)
