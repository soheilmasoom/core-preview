from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q, F, UniqueConstraint

from ledger.exceptions import InsufficientBalance, InsufficientDebt
from ledger.utils.external_price import SELL
from ledger.utils.fields import get_amount_field, get_group_id_field
from ledger.utils.wallet_pipeline import WalletPipeline


class Wallet(models.Model):
    SPOT, MARGIN, LOAN, STAKE, VOUCHER, DEBT = 'spot', 'margin', 'loan', 'stake', 'voucher', 'debt'
    MARKETS = (SPOT, MARGIN, LOAN, STAKE, VOUCHER, DEBT)
    MARKET_CHOICES = tuple((m, m) for m in MARKETS)
    NEGATIVE_MARKETS = (LOAN, DEBT)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    account = models.ForeignKey('accounts.Account', on_delete=models.PROTECT)
    asset = models.ForeignKey('ledger.Asset', on_delete=models.PROTECT, limit_choices_to={'enable': True})

    market = models.CharField(
        max_length=8,
        choices=MARKET_CHOICES,
        db_index=True,
    )

    check_balance = models.BooleanField(default=True)
    balance = get_amount_field(default=Decimal(0), validators=())
    locked = get_amount_field(default=Decimal(0))

    variant = get_group_id_field(null=True, default=None, db_index=True)
    expiration = models.DateTimeField(null=True, blank=True)
    credit = get_amount_field(default=0)

    @property
    def is_for_strategy(self):
        if not self.variant:
            return False
        return ReserveWallet.objects.filter(group_id=self.variant).exists()

    def __str__(self):
        market_verbose = dict(self.MARKET_CHOICES)[self.market]
        return '%s Wallet %s %s [%s] %s' % (market_verbose, self.asset, self.variant, self.account, self.balance)

    class Meta:
        constraints = [
            UniqueConstraint(
                name='uniqueness_without_variant_constraint',
                fields=('account', 'asset', 'market'),
                condition=Q(variant__isnull=True),
            ),
            UniqueConstraint(
                name='uniqueness_with_variant_constraint',
                fields=('account', 'asset', 'market', 'variant'),
                condition=Q(variant__isnull=False),
            ),
            CheckConstraint(
                name='valid_balance_constraint',
                check=Q(check_balance=False) |
                      (~Q(market__in=('loan', 'debt', 'margin')) & Q(balance__gte=F('locked') - F('credit'))) |
                      (Q(market__in=('loan', 'debt')) & Q(balance__lte=0) & Q(locked=0)) |
                      (Q(market='margin') & Q(variant__isnull=True) & Q(balance__gte=F('locked') - F('credit'))) |
                      (Q(market='margin') & Q(variant__isnull=False))
            ),
            CheckConstraint(
                name='valid_locked_constraint',
                check=Q(locked__gte=0),
            ),
        ]

    def get_free(self) -> Decimal:
        return self.balance - self.locked

    def has_balance(self, amount: Decimal, raise_exception: bool = False, check_system_wallets: bool = False,
                    pipeline_balance_diff=Decimal(0)) -> bool:
        assert amount >= 0 and self.market not in Wallet.NEGATIVE_MARKETS

        if not check_system_wallets and not self.check_balance:
            can = True
        else:
            can = self.get_free() + pipeline_balance_diff - amount >= -self.credit

        if raise_exception and not can:
            raise InsufficientBalance()

        return can

    def has_debt(self, amount: Decimal, raise_exception: bool = False) -> bool:
        assert amount <= 0 and self.market in Wallet.NEGATIVE_MARKETS

        can = -self.balance >= -amount

        if raise_exception and not can:
            raise InsufficientDebt()

        return can

    def has_any_debt(self) -> bool:
        assert self.market in Wallet.NEGATIVE_MARKETS
        return self.balance < 0

    def airdrop(self, amount: Decimal, i_am_sure: bool = False):
        assert settings.DEBUG_OR_TESTING or i_am_sure
        from accounts.models import Account

        from ledger.models import Trx
        from uuid import uuid4

        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=self.asset.get_wallet(Account.out()),
                receiver=self,
                amount=amount,
                group_id=uuid4(),
                scope=Trx.AIRDROP
            )

    def seize_funds(self, amount: Decimal = None):
        from ledger.models import Trx
        from uuid import uuid4
        from accounts.models import Account

        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=self,
                receiver=self.asset.get_wallet(Account.system()),
                amount=amount or self.balance,
                group_id=uuid4(),
                scope=Trx.SEIZE
            )

    def reserve_funds(self, amount: Decimal, request_id: str):
        assert self.market in (Wallet.SPOT, Wallet.MARGIN)
        assert self.variant is None  # means its not reserved wallet

        from ledger.models import Trx

        if request_id:
            existing_reserve = ReserveWallet.objects.filter(request_id=request_id).first()
            if existing_reserve:
                return existing_reserve.group_id

        if self.has_balance(amount, raise_exception=True):
            group_id = uuid4()
            with WalletPipeline() as pipeline:
                child_wallet = Wallet.objects.create(
                    account=self.account,
                    asset=self.asset,
                    market=self.market,
                    variant=group_id,
                )
                pipeline.new_trx(
                    sender=self,
                    receiver=child_wallet,
                    amount=amount,
                    group_id=group_id,
                    scope=Trx.RESERVE
                )
                ReserveWallet.objects.create(
                    sender=self,
                    receiver=child_wallet,
                    amount=amount,
                    group_id=group_id,
                    request_id=request_id,
                )
                return group_id


class ReserveWallet(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    sender = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='reserve_wallet')
    receiver = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='reserved_wallet')
    amount = get_amount_field()

    group_id = get_group_id_field(db_index=True)

    refund_completed = models.BooleanField(default=False)

    request_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
    )

    def refund(self):
        if self.refund_completed:
            raise Exception('Cannot refund already refunded wallet')

        with WalletPipeline() as pipeline:
            from ledger.models import Trx
            for child_wallet in Wallet.objects.filter(variant=self.group_id, balance__gt=0):
                if child_wallet.locked > 0:
                    raise Exception(f'Cannot refund wallet with locked balance {child_wallet.id} {child_wallet.locked}')
                parent_wallet = child_wallet.asset.get_wallet(child_wallet.account, child_wallet.market)
                pipeline.new_trx(
                    sender=child_wallet,
                    receiver=parent_wallet,
                    amount=child_wallet.balance,
                    group_id=self.group_id,
                    scope=Trx.RESERVE
                )
            self.refund_completed = True
            self.save(update_fields=['refund_completed'])
            return True

    class Meta:
        unique_together = ('group_id', 'sender', 'receiver')

    def save(self, *args, **kwargs):
        assert self.sender.asset == self.receiver.asset
        assert self.sender != self.receiver
        assert self.amount > 0

        return super(ReserveWallet, self).save(*args, **kwargs)
