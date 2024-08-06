import logging
from uuid import uuid4

from django.db import models
from django.db.models import CheckConstraint, Q

from accounts.models import Account
from ledger.models import Trx, Asset, Wallet
from ledger.utils.fields import get_amount_field
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)


class Prize(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    achievement = models.ForeignKey('gamify.Achievement', on_delete=models.CASCADE)
    account = models.ForeignKey(to=Account, on_delete=models.CASCADE, verbose_name='کاربر')
    group_id = models.UUIDField(default=uuid4, db_index=True)

    amount = get_amount_field()
    asset = models.ForeignKey(to=Asset, on_delete=models.CASCADE)
    voucher_expiration = models.DateTimeField(null=True, blank=True)
    redeemed = models.BooleanField(default=False)

    fake = models.BooleanField(default=False)
    variant = models.CharField(null=True, blank=True, max_length=16)
    value = get_amount_field()

    class Meta:
        unique_together = [('account', 'achievement', 'variant')]
        constraints = [CheckConstraint(check=Q(amount__gte=0), name='check_ledger_prize_amount', ), ]
        permissions = [
            ("list_prize", "Can list prize"),
        ]

    def build_trx(self, pipeline: WalletPipeline):
        if self.redeemed:
            logger.info('Ignored redeem prize because it is redeemed before.')
            return

        self.redeemed = True
        self.save(update_fields=['redeemed'])

        system = Account.system()

        if self.voucher_expiration:
            market = Wallet.VOUCHER
            expiration = self.voucher_expiration
        else:
            market = Wallet.SPOT
            expiration = None

        assert market == Wallet.VOUCHER or not self.asset.symbol == Asset.USDT

        receiver = self.asset.get_wallet(self.account, market=market, expiration=expiration)

        pipeline.new_trx(
            group_id=self.group_id,
            sender=self.asset.get_wallet(system),
            receiver=receiver,
            amount=self.amount,
            scope=Trx.PRIZE
        )

        if market == Wallet.VOUCHER and receiver.expiration < expiration:
            receiver.expiration = expiration
            receiver.save(update_fields=['expiration'])

    def __str__(self):
        return '%s %s %s' % (self.account, self.amount, self.asset)
