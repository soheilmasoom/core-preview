from django.db import models, transaction
from simple_history.models import HistoricalRecords

from accounts.models import User
from ledger.models import Asset, Network, Transfer
from ledger.utils.fields import get_amount_field, get_address_field, get_status_field, PROCESS, DONE, CANCELED, PENDING
from ledger.utils.price import get_last_price


class DepositRecoveryRequest(models.Model):
    SYSTEM, USER = 'sys', 'user'

    history = HistoricalRecords()

    created = models.DateTimeField(auto_now_add=True)
    status = get_status_field(default=PROCESS)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    network = models.ForeignKey(Network, on_delete=models.PROTECT)
    memo = models.CharField(max_length=64, blank=True)
    trx_hash = models.CharField(max_length=128)
    amount = get_amount_field()
    receiver_address = get_address_field()
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=4, db_index=True, choices=[(SYSTEM, SYSTEM), (USER, USER)], default=USER)
    blocklink_id = models.IntegerField(null=True, unique=True)

    verifier = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    image = models.OneToOneField(
        to='multimedia.Image',
        on_delete=models.PROTECT,
        verbose_name='تصویر جزییات برداشت',
        related_name='+',
        blank=True,
        null=True
    )

    comment = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("manage_deposit_recovery", "Manage Deposit Recovery Request"),
        ]

    def verify(self, verifier: User):
        if self.status != PROCESS:
            return True

        if not self.trx_hash:
            return False

        if Transfer.objects.filter(
            trx_hash=self.trx_hash,
            deposit=False,
        ).exclude(status=CANCELED).exists():
            return False

        self.status = PENDING
        self.verifier = verifier
        self.save(update_fields=['status', 'verifier'])

        return True

    def create_transfer(self):
        with transaction.atomic():
            recovery = DepositRecoveryRequest.objects.get(id=self.id).select_for_update()

            if recovery.status not in (PROCESS, PENDING):
                return

            if not recovery.trx_hash:
                return

            recovery.status = DONE
            recovery.save(update_fields=['status'])

            wallet = recovery.asset.get_wallet(account=recovery.user.get_account())
            price_usdt = get_last_price(wallet.asset.symbol + Asset.USDT) or 0
            price_irt = get_last_price(wallet.asset.symbol + Asset.IRT) or 0
            transfer = Transfer.objects.create(
                network=recovery.network,
                memo=recovery.memo,
                amount=recovery.amount,
                wallet=wallet,
                source=Transfer.MANUAL,
                out_address='',
                deposit=True,
                usdt_value=recovery.amount * price_usdt,
                irt_value=recovery.amount * price_irt,
                trx_hash=recovery.trx_hash,
            )
            transfer.accept()
