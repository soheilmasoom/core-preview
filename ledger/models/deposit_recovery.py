from django.db import models, transaction

from accounts.models import User
from ledger.models import Asset, Network, Transfer
from ledger.utils.fields import get_amount_field, get_address_field, get_status_field, PENDING, PROCESS, CANCELED, DONE
from ledger.utils.price import get_last_price


class DepositRecoveryRequest(models.Model):
    SYSTEM, USER = 'sys', 'user'

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
    block_link_id = models.IntegerField(null=True, unique=True)

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

    def create_transfer(self):
        with transaction.atomic():
            self.status = DONE
            self.save(update_fields=['status'])
            wallet = self.asset.get_wallet(account=self.user.get_account())
            price_usdt = get_last_price(wallet.asset.symbol + Asset.USDT) or 0
            price_irt = get_last_price(wallet.asset.symbol + Asset.IRT) or 0
            transfer = Transfer.objects.create(
                network=self.network,
                memo=self.memo,
                amount=self.amount,
                wallet=wallet,
                source=Transfer.MANUAL,
                out_address='',
                deposit=True,
                usdt_value=self.amount * price_usdt,
                irt_value=self.amount * price_irt,
                trx_hash=self.trx_hash,
            )
            transfer.accept()
