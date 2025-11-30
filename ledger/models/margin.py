from uuid import uuid4

from django.db import models
from rest_framework import serializers

from accounts.models import Account
from ledger.exceptions import InsufficientBalance
from ledger.models import Asset, Wallet, Trx
from ledger.utils.external_price import LONG
from ledger.utils.fields import get_amount_field
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol

BORROW, REPAY, OPEN = 'borrow', 'repay', 'open'


class MarginTransfer(models.Model):
    SPOT_TO_MARGIN = 'sm'
    MARGIN_TO_SPOT = 'ms'
    MARGIN_TO_POSITION = 'mp'
    POSITION_TO_MARGIN = 'pm'

    created = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey(to=Account, on_delete=models.CASCADE)

    amount = get_amount_field()

    type = models.CharField(
        max_length=2,
        choices=(
            (SPOT_TO_MARGIN, 'spot to margin'), (MARGIN_TO_SPOT, 'margin to spot'),
            (MARGIN_TO_POSITION, 'margin to position'), (POSITION_TO_MARGIN, 'position to margin')),
    )

    asset = models.ForeignKey(to=Asset, on_delete=models.PROTECT)
    position_symbol = models.ForeignKey(to=PairSymbol, null=True, blank=True, on_delete=models.PROTECT)
    position = models.ForeignKey('ledger.MarginPosition', on_delete=models.CASCADE, blank=True, null=True)

    group_id = models.UUIDField(default=uuid4)

    def save(self, *args, **kwargs):
        spot_wallet = self.asset.get_wallet(self.account, Wallet.SPOT)
        margin_wallet = self.asset.get_wallet(self.account, Wallet.MARGIN)
        position_wallet = None
        pipeline_balance_diff = 0

        if self.type in (self.MARGIN_TO_POSITION, self.POSITION_TO_MARGIN):
            if not self.position_symbol:
                raise ValueError('position_symbol is required')
            from ledger.models import MarginPosition

            if not self.position or self.position.status != MarginPosition.OPEN:
                raise ValueError('No open position found for this symbol')
            position_wallet = self.asset.get_wallet(self.account, Wallet.MARGIN, self.position.group_id)

        from ledger.models import MarginHistoryModel
        if self.type == self.SPOT_TO_MARGIN:
            sender, receiver = spot_wallet, margin_wallet
            MarginHistoryModel.objects.create(
                asset=self.asset,
                amount=self.amount,
                group_id=self.group_id,
                type=MarginHistoryModel.POSITION_TRANSFER,
                account=self.account
            )

        elif self.type == self.MARGIN_TO_SPOT:
            # todo :: check margin positive equity

            sender, receiver = margin_wallet, spot_wallet
            MarginHistoryModel.objects.create(
                asset=self.asset,
                amount=-self.amount,
                group_id=self.group_id,
                type=MarginHistoryModel.POSITION_TRANSFER,
                account=self.account
            )

        elif self.type == self.MARGIN_TO_POSITION:
            sender, receiver = margin_wallet, position_wallet

            self.position.equity += self.amount

        elif self.type == self.POSITION_TO_MARGIN:
            sender, receiver = position_wallet, margin_wallet
            # todo :: check margin positive equity

            if self.position.withdrawable_base_asset < self.amount:
                raise InsufficientBalance

            self.position.equity -= self.amount
        else:
            raise NotImplementedError

        with WalletPipeline() as pipeline:
            position = self.position

            if self.type == self.POSITION_TO_MARGIN and position and position.side == LONG:  # todo :: add doc
                from ledger.models import MarginPosition
                position = MarginPosition.objects.select_for_update().get(id=position.id)
                pipeline_balance_diff = position.withdrawable_base_asset + position.debt_amount
                position.equity = self.position.equity

            sender.has_balance(self.amount, raise_exception=True, pipeline_balance_diff=pipeline_balance_diff)

            super(MarginTransfer, self).save(*args)

            pipeline.new_trx(sender, receiver, self.amount, Trx.MARGIN_TRANSFER, self.group_id)
            if position:
                position.set_liquidation_price(pipeline)
                position.save(update_fields=['equity', 'liquidation_price'])


class SymbolField(serializers.CharField):
    def to_representation(self, value: PairSymbol):
        if value:
            return value.name

    def to_internal_value(self, data: str):
        if not data:
            return
        else:
            return PairSymbol.get_by(name=data)
