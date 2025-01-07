from uuid import uuid4

from django.db import models
from django.core.validators import MinValueValidator

from accounts.models import Account
from ledger.models import Trx, Wallet
from ledger.utils.wallet_pipeline import WalletPipeline


class PreciousMetalChoices:
    GOLD = 'XAU'
    SILVER = 'XAG'

    CHOICES = [
        (GOLD, 'Gold'),
        (SILVER, 'Silver'),
    ]


class Treasury(models.Model):
    metal_type = models.CharField(
        max_length=10,
        choices=PreciousMetalChoices.CHOICES,
        unique=True,
        verbose_name="Metal Type"
    )
    current_balance = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Current Balance (grams)"
    )
    sold_amount = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Sold Amount (grams)"
    )
    bank_reserved = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Bank Reserved Amount (grams)"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "خزانه"
        verbose_name_plural = "خزانه"

    def __str__(self):
        return f"{self.get_metal_type_display()} Treasury"


class PhysicalWithdrawStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    COMPLETED = 'completed'

    CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
        (COMPLETED, 'Completed')
    ]


class PhysicalWithdraw(models.Model):
    account = models.ForeignKey('accounts.Account', on_delete=models.PROTECT)
    asset = models.ForeignKey('ledger.Asset', on_delete=models.PROTECT)
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Amount (grams)"
    )
    status = models.CharField(
        max_length=10,
        choices=PhysicalWithdrawStatus.CHOICES,
        default=PhysicalWithdrawStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    lock_id = models.UUIDField(unique=True)

    def approve(self) -> bool:
        if self.status != PhysicalWithdrawStatus.PENDING:
            raise ValueError('Only pending withdrawals can be approved')

        self.status = PhysicalWithdrawStatus.APPROVED
        self.save(update_fields=['status', 'updated_at'])
        return True

    def reject(self) -> bool:
        if self.status != PhysicalWithdrawStatus.PENDING:
            raise ValueError('Only pending withdrawals can be rejected')

        try:
            with WalletPipeline() as pipeline:
                pipeline.release_lock(self.lock_id)
                self.status = PhysicalWithdrawStatus.REJECTED
                self.save(update_fields=['status', 'updated_at'])
                return True
        except Exception as e:
            raise ValueError(f'Failed to reject withdrawal: {str(e)}')

    def complete(self) -> bool:
        if self.status != PhysicalWithdrawStatus.APPROVED:
            raise ValueError('Only approved withdrawals can be completed')

        try:
            with WalletPipeline() as pipeline:
                pipeline.release_lock(self.lock_id)

                user_wallet = self.asset.get_wallet(self.account, market=Wallet.SPOT, variant=None)
                out_wallet = self.asset.get_wallet(Account.out(), market=Wallet.SPOT, variant=None)

                pipeline.new_trx(
                    sender=user_wallet,
                    receiver=out_wallet,
                    amount=self.amount,
                    scope=Trx.TRANSFER,
                    group_id=uuid4()
                )

                self.status = PhysicalWithdrawStatus.COMPLETED
                self.save(update_fields=['status', 'updated_at'])
                return True
        except Exception as e:
            raise ValueError(f'Failed to complete withdrawal: {str(e)}')

    def __str__(self):
        return f"{self.account} - {self.asset} - {self.amount}g - {self.status}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "دریافت فیزیکی"
        verbose_name_plural = "دریافت های فیزیکی"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['account', 'status']),
        ]
