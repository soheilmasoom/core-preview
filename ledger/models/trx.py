import logging
from uuid import uuid4

from django.db import models
from django.db.models import CheckConstraint, Q

from ledger.utils.fields import get_amount_field

logger = logging.getLogger(__name__)


class Trx(models.Model):
    TRADE = 't'
    TRANSFER = 'f'
    MARGIN_TRANSFER = 'm'
    MARGIN_BORROW = 'b'
    MARGIN_INSURANCE = 'mi'
    MARGIN_INTEREST = 'in'
    CLOSE_MARGIN = 'cm'
    FAST_LIQUID = 'fl'
    LIQUID = 'l'
    COMMISSION = 'c'
    PRIZE = 'p'
    REVERT = 'r'
    AIRDROP = 'ad'
    SEIZE = 'sz'
    RESERVE = 'rs'
    STAKE_REVENUE = 'sr'
    STAKE = 'st'
    STAKE_FEE = 'sf'
    FIX = 'fx'
    DEBT_CLEAR = 'dc'
    DUST = 'du'
    MANUAL = 'mn'
    DELIST = 'dl'
    REBRAND = 'rb'
    TOKEN_TRANSFER = 'tt'

    SCOPES_VERBOSE = {
        TRADE: 'trade',
        TRANSFER: 'transfer',
        MARGIN_TRANSFER: 'margin_transfer',
        MARGIN_BORROW: 'margin_borrow',
        MARGIN_INSURANCE: 'margin_insurance',
        MARGIN_INTEREST: 'margin_interest',
        CLOSE_MARGIN: 'close_margin',
        FAST_LIQUID: 'fast_liquid',
        LIQUID: 'liquid',
        COMMISSION: 'fee',
        PRIZE: 'prize',
        REVERT: 'revert',
        AIRDROP: 'airdrop',
        SEIZE: 'seize',
        RESERVE: 'reserve',
        STAKE_REVENUE: 'stake_revenue',
        STAKE: 'stake',
        STAKE_FEE: 'stake_fee',
        FIX: 'fix',
        DEBT_CLEAR: 'debt_clear',
        DUST: 'dust',
        MANUAL: 'manual',
        DELIST: 'delist',
        REBRAND: 'rebrand',
        TOKEN_TRANSFER: 'token_transfer'
    }

    created = models.DateTimeField(auto_now_add=True)

    sender = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='sent_trx')
    receiver = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='received_trx')
    amount = get_amount_field()

    group_id = models.UUIDField(default=uuid4, db_index=True)

    scope = models.CharField(
        max_length=2,
        choices=SCOPES_VERBOSE.items()
    )

    def revert(self, pipeline):
        pipeline.new_trx(
            sender=self.receiver,
            receiver=self.sender,
            amount=self.amount,
            group_id=self.group_id,
            scope=Trx.REVERT
        )

    class Meta:
        unique_together = ('group_id', 'sender', 'receiver', 'scope')
        constraints = [
            CheckConstraint(check=Q(amount__gt=0), name='check_ledger_trx_amount', ),
        ]
        indexes = [
            models.Index(fields=['scope', 'sender', 'created'], name="trx_margin_idx")
        ]

        permissions = [
            ("list_trx", "Can list trx"),
        ]

    def save(self, *args, **kwargs):
        assert self.sender.asset == self.receiver.asset
        assert self.sender != self.receiver
        assert self.amount > 0

        return super(Trx, self).save(*args, **kwargs)
