import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from decouple import config
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import UniqueConstraint, Q, Sum

from _base.settings import SYSTEM_ACCOUNT_ID
from accounts.models import Account, SystemConfig
from ledger.models import Trx
from ledger.utils.external_price import SHORT, LONG, BUY, SELL, get_other_side
from ledger.utils.fields import get_amount_field
from ledger.utils.precision import floor_precision, ceil_precision
from ledger.utils.price import get_depth_price, get_base_depth_price, get_price
from market.models import PairSymbol

logger = logging.getLogger(__name__)

MARGIN_INSURANCE_ACCOUNT = config('MARGIN_INSURANCE_ACCOUNT', cast=int)
MARGIN_POOL_ACCOUNT = config('MARGIN_POOL_ACCOUNT', cast=int)


class MarginPosition(models.Model):
    OPEN, CLOSED, TERMINATING = 'open', 'closed', 'terminating'
    STATUS_LIST = [OPEN, CLOSED, TERMINATING]
    STATUS_CHOICES = [(OPEN, OPEN), (CLOSED, CLOSED), (TERMINATING, TERMINATING)]
    SIDE_CHOICES = [(LONG, LONG), (SHORT, SHORT)]

    created = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey('accounts.Account', on_delete=models.PROTECT)
    asset_wallet = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='asset_wallet')
    base_wallet = models.ForeignKey('ledger.Wallet', on_delete=models.PROTECT, related_name='base_wallet')
    group_id = models.UUIDField(default=uuid.uuid4)

    symbol = models.ForeignKey('market.PairSymbol', on_delete=models.PROTECT)
    amount = get_amount_field(default=0)
    equity = get_amount_field(default=0)
    average_price = get_amount_field(default=0)
    liquidation_price = get_amount_field(null=True)
    side = models.CharField(max_length=8, choices=SIDE_CHOICES)
    status = models.CharField(default=OPEN, max_length=12, choices=STATUS_CHOICES)
    leverage = models.PositiveSmallIntegerField()
    alert_mode = models.BooleanField(default=False, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'symbol', 'liquidation_price'], name="position_idx")
        ]

    def __str__(self):
        return f'{self.side} {self.symbol} X{self.leverage} (eq={self.equity})'

    @property
    def loan_wallet(self):
        if self.side == SHORT:
            wallet = self.asset_wallet
        elif self.side == LONG:
            wallet = self.base_wallet
        else:
            raise NotImplementedError
        wallet.refresh_from_db()
        return wallet

    @property
    def debt_amount(self):
        return -self.loan_wallet.balance

    @property
    def base_debt_amount(self):
        wallet = self.loan_wallet
        if self.side == SHORT:
            return wallet.balance * self.symbol.last_trade_price
        elif self.side == LONG:
            return wallet.balance
        else:
            raise NotImplementedError

    @property
    def margin_wallet(self):
        if self.side == SHORT:
            wallet = self.base_wallet
        elif self.side == LONG:
            wallet = self.asset_wallet
        else:
            raise NotImplementedError
        wallet.refresh_from_db()
        return wallet

    @property
    def total_balance(self):
        return self.margin_wallet.balance

    @property
    def base_total_balance(self):
        wallet = self.margin_wallet
        if self.side == SHORT:
            return wallet.balance
        elif self.side == LONG:
            return wallet.balance * self.symbol.last_trade_price
        else:
            raise NotImplementedError

    @property
    def withdrawable_base_asset(self):
        if self.side == SHORT:
            base_total_balance = abs(Decimal('2') * self.base_debt_amount)
            amount = max(self.base_total_balance - base_total_balance, Decimal('0'))
        else:
            total_debt = abs(Decimal('0.5') * self.base_total_balance)
            amount = max(total_debt + self.base_debt_amount, Decimal('0'))
        return floor_precision(Decimal(amount), self.symbol.tick_size)

    def get_ratio(self) -> Decimal:
        from accounts.models import SystemConfig
        sys_config = SystemConfig.get_system_config()

        if self.side == SHORT:
            return 1 / sys_config.liquidation_level
        elif self.side == LONG:
            return sys_config.liquidation_level
        else:
            raise NotImplementedError

    def set_liquidation_price(self, pipeline=None):
        debt_amount = self.debt_amount - pipeline.get_wallet_balance_diff(self.loan_wallet.id)
        total_balance = self.total_balance + pipeline.get_wallet_balance_diff(self.margin_wallet.id)

        if debt_amount > Decimal('0') and total_balance:
            if self.side == SHORT:
                self.liquidation_price = total_balance / debt_amount * self.get_ratio()
            elif self.side == LONG:
                self.liquidation_price = debt_amount / total_balance * self.get_ratio()
            else:
                raise NotImplementedError
        else:
            self.liquidation_price = None

    def rebalance(self, pipeline, price: Decimal = None):
        from ledger.models import Wallet

        debt_amount = self.debt_amount - pipeline.get_wallet_balance_diff(self.loan_wallet.id)
        total_balance = self.total_balance + pipeline.get_wallet_balance_diff(self.margin_wallet.id)

        if total_balance and debt_amount:
            if self.side == SHORT:
                liquidation_price = total_balance / debt_amount * self.get_ratio()
                ratio = Decimal(1 - self.liquidation_price / liquidation_price)
                amount = total_balance * ratio
            elif self.side == LONG:
                liquidation_price = debt_amount / total_balance * self.get_ratio()
                ratio = Decimal(self.liquidation_price / liquidation_price - 1)
                amount = debt_amount * ratio
            else:
                return
        else:
            return

        if amount > Decimal('0'):
            group_id = uuid.uuid4()
            pipeline.new_trx(
                sender=self.base_wallet,
                receiver=self.symbol.base_asset.get_wallet(self.account, Wallet.MARGIN, None),
                amount=amount,
                group_id=group_id,
                scope=Trx.MARGIN_TRANSFER
            )

            self.create_transfer_equity_history(amount=amount, total_balance=total_balance, debt_amount=debt_amount,
                                                group_id=group_id, price=price)

    def create_transfer_equity_history(self, amount, total_balance, debt_amount, group_id, price: Decimal = None):

        if not price:
            price = self.symbol.last_trade_price

        if self.side == LONG:
            total_value, debt_value = price * total_balance, debt_amount
        else:
            total_value, debt_value = total_balance, price * debt_amount

        position_value = total_value - debt_value

        if position_value:
            to_transfer_equity = amount * (self.equity / position_value)
        else:
            to_transfer_equity = Decimal('0')

        realized_pnl = amount - to_transfer_equity

        self.create_history(
            asset=self.symbol.base_asset,
            amount=realized_pnl,
            group_id=group_id,
            type=MarginHistoryModel.PNL
        )

        self.equity -= to_transfer_equity
        self.save(update_fields=['equity'])

    @classmethod
    def get_by(cls, symbol: PairSymbol, account: Account, order_side: str, is_open_position: bool):
        assert order_side is not None

        if is_open_position:
            position_side = SHORT if order_side == SELL else LONG
        else:
            position_side = SHORT if order_side == BUY else LONG

        from ledger.models import Wallet
        position = cls.objects.filter(
            account=account,
            symbol=symbol,
            status__in=[cls.OPEN, cls.TERMINATING],
            side=position_side
        ).first()

        if position:
            return position
        else:
            group_id = uuid.uuid5(uuid.NAMESPACE_X500, f'{account.id}-{symbol.name}-{position_side}')

            margin_leverage, _ = MarginLeverage.objects.get_or_create(
                account=account,
                defaults={
                    'leverage': SystemConfig.get_system_config().default_margin_leverage
                }
            )

            return cls.objects.create(
                account=account,
                symbol=symbol,
                status=cls.OPEN,
                group_id=group_id,
                base_wallet=symbol.base_asset.get_wallet(account, Wallet.MARGIN, group_id),
                asset_wallet=symbol.asset.get_wallet(account, Wallet.MARGIN, group_id),
                side=position_side,
                leverage=margin_leverage.leverage
            )

    def get_insurance_wallet(self):
        return self.symbol.base_asset.get_wallet(account=MARGIN_INSURANCE_ACCOUNT)

    def get_margin_pool_wallet(self):
        return self.loan_wallet.asset.get_wallet(account=Account.objects.get(id=MARGIN_POOL_ACCOUNT))

    def get_interest_rate(self):
        return self.loan_wallet.asset.margin_interest_fee

    def liquidate(self, pipeline, charge_insurance: bool = True):
        if self.status != self.OPEN:
            return

        if charge_insurance:
            self.status = self.TERMINATING
            self.save(update_fields=['status'])

        from market.utils.order_utils import Order, new_order
        from ledger.models import Trx, Wallet

        Order.cancel_orders(Order.open_objects.filter(wallet__in=[self.base_wallet, self.asset_wallet]))

        loan_wallet_balance_diff = pipeline.get_wallet_balance_diff(self.loan_wallet.id)

        to_close_amount = ceil_precision((self.debt_amount - loan_wallet_balance_diff)
                                         / (1 - self.symbol.get_fee_rate(self.account, is_maker=False)), self.symbol.step_size)
        if self.side == SHORT:
            side = BUY
            price = get_depth_price(
                symbol=self.symbol.name,
                side=get_other_side(side),
                amount=to_close_amount,
                depth_check=False
            )
        else:
            side = SELL
            price = get_base_depth_price(
                symbol=self.symbol.name,
                side=get_other_side(side),
                amount=to_close_amount,
                depth_check=False
            )

        free_amount = floor_precision(self.margin_wallet.get_free(), self.symbol.step_size)

        if self.side == SHORT:
            free_amount /= price
        elif self.side == LONG:
            to_close_amount /= price
        else:
            raise NotImplementedError

        loss_amount = Decimal('0')
        group_id = uuid.uuid4()

        if self.side == SHORT:
            loss_amount = (to_close_amount - free_amount) * Decimal('1.05') * price
            if loss_amount > 0:
                pipeline.new_trx(
                    sender=self.get_insurance_wallet(),
                    receiver=self.base_wallet,
                    amount=loss_amount,
                    scope=Trx.MARGIN_INSURANCE,
                    group_id=group_id,
                )
                to_close_amount = ceil_precision(to_close_amount, self.symbol.step_size)
        else:
            to_close_amount = floor_precision(free_amount, self.symbol.step_size)

        liquidation_order = None
        if to_close_amount > 0:
            liquidation_order = new_order(
                pipeline=pipeline,
                symbol=self.symbol,
                account=self.account,
                amount=to_close_amount,
                fill_type=Order.MARKET,
                side=side,
                market=Wallet.MARGIN,
                variant=self.group_id,
                pass_min_notional=True,
                order_type=Order.LIQUIDATION if charge_insurance else Order.ORDINARY,
                parent_lock_group_id=group_id,
                margin_position=self
            )

        self.base_wallet.refresh_from_db()
        remaining_base_asset = self.base_wallet.balance + pipeline.get_wallet_balance_diff(self.base_wallet.id)

        charged_amount = 0
        if self.side == SHORT:
            if not charge_insurance and remaining_base_asset < loss_amount:
                logger.warning(f"Position:{self.id} charged in close mode !!!")

            if remaining_base_asset > 0 and loss_amount > 0:
                pipeline.new_trx(
                    self.base_wallet,
                    self.get_insurance_wallet(),
                    min(loss_amount, remaining_base_asset),
                    Trx.MARGIN_INSURANCE,
                    group_id,
                )
                charged_amount = min(loss_amount, remaining_base_asset) - loss_amount
        else:
            if remaining_base_asset < 0:
                pipeline.new_trx(
                    sender=self.get_insurance_wallet(),
                    receiver=self.base_wallet,
                    amount=-remaining_base_asset,
                    scope=Trx.MARGIN_INSURANCE,
                    group_id=group_id,
                )
                charged_amount = -remaining_base_asset

        if charged_amount != 0:
            self.create_history(
                asset=self.symbol.base_asset,
                amount=charged_amount,
                group_id=group_id,
                type=MarginHistoryModel.INSURANCE_FEE
            )

        if liquidation_order:
            liquidation_order.refresh_from_db()

            if liquidation_order.filled_amount >= to_close_amount:
                self.amount = 0
                self.status = self.CLOSED
            else:

                filled_amount = liquidation_order.filled_amount if self.side == SHORT else liquidation_order.filled_amount * liquidation_order.price

                loan_wallet = self.loan_wallet
                debt_amount = -loan_wallet.balance + pipeline.get_wallet_balance_diff(loan_wallet.id)

                self.amount = max(debt_amount - filled_amount, Decimal('0'))

                if not charge_insurance:
                    logger.warning(f'Position:{self.id} doesnt close in Liquidation Process Due to Order'
                                   f' filled amount{filled_amount}/{debt_amount}')

            if liquidation_order.filled_amount == 0 and liquidation_order.status == Order.CANCELED:
                self.status = self.OPEN
                logger.warning(f"Position:{self.id} closing order:{liquidation_order.id} didnt fill")
        else:
            self.amount = 0
            self.status = self.CLOSED

        self.save(update_fields=['amount', 'status'])
        self.set_liquidation_price(pipeline)

        if charge_insurance:
            from ledger.utils.margin import alert_liquidate
            alert_liquidate(self)

    @classmethod
    def check_for_liquidation(cls, order, min_price, max_price, pipeline):
        to_liquid_short_positions = cls.objects.filter(
            side=SHORT,
            status=cls.OPEN,
            symbol=order.symbol,
            liquidation_price__lte=max_price,
        ).order_by('liquidation_price')

        for position in to_liquid_short_positions:
            position.liquidate(pipeline)

        to_liquid_long_positions = cls.objects.filter(
            side=LONG,
            status=cls.OPEN,
            symbol=order.symbol,
            liquidation_price__gte=min_price,
        ).order_by('liquidation_price')

        for position in to_liquid_long_positions:
            position.liquidate(pipeline)

    def create_history(self, asset, amount: Decimal, type: str, group_id: uuid = None):
        assert type in MarginHistoryModel.type_list
        if amount:
            MarginHistoryModel.objects.create(
                position=self,
                asset=asset,
                amount=amount,
                type=type,
                group_id=group_id or uuid.uuid4(),
                account=self.account
            )

    def get_base_trade_fee(self) -> Decimal:
        asset_fee = Decimal(MarginHistoryModel.objects.filter(
            position=self,
            type=MarginHistoryModel.TRADE_FEE,
            asset=self.symbol.asset
        ).aggregate(s=Sum('amount'))['s'] or 0)

        asset_fee *= self.symbol.last_trade_price

        base_asset_fee = Decimal(MarginHistoryModel.objects.filter(
            position=self,
            type=MarginHistoryModel.TRADE_FEE,
            asset=self.symbol.base_asset
        ).aggregate(s=Sum('amount'))['s'] or 0)
        return asset_fee + base_asset_fee

    def convert_dust(self, pipeline):
        group_id = uuid.uuid4()
        self.asset_wallet.refresh_from_db()

        price = get_price(
            self.asset_wallet.asset.symbol + self.base_wallet.asset.symbol,
            side=BUY,
        )

        if price is None:
            return

        free = self.asset_wallet.get_free() + pipeline.get_wallet_balance_diff(self.asset_wallet.id)

        if free > 0:
            pipeline.new_trx(
                sender=self.asset_wallet,
                receiver=self.asset_wallet.asset.get_wallet(SYSTEM_ACCOUNT_ID),
                amount=free,
                group_id=group_id,
                scope=Trx.DUST
            )

            pipeline.new_trx(
                sender=self.base_wallet.asset.get_wallet(SYSTEM_ACCOUNT_ID),
                receiver=self.base_wallet,
                amount=price * free,
                group_id=group_id,
                scope=Trx.DUST,
            )

            MarginHistoryModel.objects.create(
                asset=self.base_wallet.asset,
                amount=free,
                group_id=group_id,
                type=MarginHistoryModel.DUST,
                account=self.account
            )


class MarginLeverage(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    account = models.ForeignKey('accounts.Account', on_delete=models.CASCADE, unique=True)
    leverage = models.PositiveSmallIntegerField(default=3, validators=(MinValueValidator(1),))

    def __str__(self):
        return f'{self.account}-{self.leverage}'


@dataclass
class MarginPositionTradeInfo:
    loan_type: str
    position: MarginPosition
    order_side: str
    trade_amount: Decimal = 0
    trade_price: Decimal = 0
    group_id: UUID = 0


class MarginHistoryModel(models.Model):
    PNL, TRANSFER, POSITION_TRANSFER, TRADE_FEE, INTEREST_FEE, INSURANCE_FEE, DUST = 'pnl', 'transfer', 'p_transfer', 'trade_fee', 'int_fee', 'ins_fee', 'dust'
    type_list = [PNL, TRANSFER, TRADE_FEE, INTEREST_FEE, INSURANCE_FEE]

    created = models.DateTimeField(auto_now_add=True)
    position = models.ForeignKey('ledger.MarginPosition', on_delete=models.CASCADE, null=True)
    account = models.ForeignKey('accounts.Account', on_delete=models.CASCADE)
    asset = models.ForeignKey('ledger.Asset', on_delete=models.CASCADE)
    amount = get_amount_field()
    type = models.CharField(
        choices=[(PNL, PNL), (TRANSFER, TRANSFER), (TRADE_FEE, TRADE_FEE), (INTEREST_FEE, INTEREST_FEE),
                 (INSURANCE_FEE, INSURANCE_FEE), (POSITION_TRANSFER, POSITION_TRANSFER), (DUST, DUST)],
        max_length=12
    )
    group_id = models.UUIDField()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['position', 'group_id', 'created'],
                name="position_group_id_created_unique",
                condition=Q(type='int_fee'),
            ),
        ]
