from django.db import models
from django.db.models import Q, CheckConstraint, UniqueConstraint

from financial.models import Payment
from ledger.utils.fields import get_status_field, DONE, get_group_id_field, CANCELED, get_iban_field, PROCESS, \
    INIT
from ledger.utils.precision import humanize_number
from ledger.utils.wallet_pipeline import WalletPipeline


class DirectDebitRequest(models.Model):
    PENDING_STATES = [INIT, PROCESS]

    created = models.DateTimeField(auto_now_add=True)

    owner = models.ForeignKey('AuthorizationId', on_delete=models.PROTECT, null=True, blank=True)
    status = get_status_field()

    gateway = models.ForeignKey('DirectDebitGateway', on_delete=models.PROTECT)

    amount = models.PositiveBigIntegerField()
    fee = models.PositiveBigIntegerField()
    balance = models.PositiveBigIntegerField(default=0)

    group_id = get_group_id_field(unique=True)
    payment = models.OneToOneField('financial.Payment', null=True, blank=True, on_delete=models.CASCADE)

    comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(status__in=[INIT, CANCELED]) | Q(owner__isnull=False),
                name='direct_debit_request_owner_null_condition'
            ),
        ]

    def __str__(self):
        return f'{self.id}- {humanize_number(self.amount)} IRT ({self.status})'

    def accept(self):
        with WalletPipeline() as pipeline:
            req = DirectDebitRequest.objects.select_for_update().get(id=self.id)

            if req.payment or req.status not in self.PENDING_STATES:
                return

            auth_id = req.owner

            req.payment = Payment.objects.create(
                group_id=req.group_id,
                user=auth_id.user,
                amount=req.amount,
                fee=req.fee,
                source=Payment.DIRECT_DEBIT,
            )
            req.payment.accept(pipeline)

            req.status = DONE
            req.save(update_fields=['status', 'payment'])
            return True

    def reject(self):
        DirectDebitRequest.objects.filter(id=self.id, status__in=self.PENDING_STATES).update(status=CANCELED)
