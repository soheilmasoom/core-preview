import logging
from decimal import Decimal
from uuid import uuid4

from django.db import models
from django.db.models import F, CheckConstraint, Q
from django.utils import timezone

from ledger.models import Wallet
from ledger.utils.external_price import BUY, SELL
from ledger.utils.fields import get_amount_field
from ledger.utils.precision import floor_precision
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)


class StopLossManager(models.Manager):
    def __init__(self, *args, **kwargs):
        self.open_only = kwargs.pop('open_only', False)
        self.not_triggered_only = kwargs.pop('not_triggered_only', False)
        super(StopLossManager, self).__init__(*args, **kwargs)

    def get_queryset(self):
        if self.open_only:
            return super().get_queryset().filter(canceled_at__isnull=True, filled_amount__lt=F('amount'))
        if self.not_triggered_only:
            return super().get_queryset().filter(canceled_at__isnull=True, filled_amount__lt=F('amount')).exclude(
                fill_type=StopLoss.LIMIT, order__isnull=False
            )
        return super().get_queryset()


class StopLoss(models.Model):
    NEW = 'new'
    TRIGGERED = 'triggered'
    FILLED = 'filled'
    BUY, SELL = 'buy', 'sell'
    SIDE_CHOICES = [(BUY, BUY), (SELL, SELL)]
    LIMIT, MARKET = 'limit', 'market'
    FILL_TYPE_CHOICES = [(LIMIT, LIMIT), (MARKET, MARKET)]

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='stop_losses')
    created = models.DateTimeField(auto_now_add=True)
    symbol = models.ForeignKey('market.PairSymbol', on_delete=models.PROTECT)
    fill_type = models.CharField(max_length=8, choices=FILL_TYPE_CHOICES)
    amount = get_amount_field()
    filled_amount = get_amount_field(default=Decimal(0))
    trigger_price = get_amount_field()
    price = get_amount_field(null=True)
    side = models.CharField(max_length=8, choices=SIDE_CHOICES)

    canceled_at = models.DateTimeField(blank=True, null=True)

    group_id = models.UUIDField(default=uuid4)

    oco = models.OneToOneField(to='market.OCO', on_delete=models.SET_NULL, null=True, blank=True)

    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def unfilled_amount(self):
        amount = self.amount - self.filled_amount
        return floor_precision(amount, self.symbol.step_size)

    @property
    def base_wallet(self):
        return self.symbol.base_asset.get_wallet(
            self.wallet.account, self.wallet.market, variant=self.wallet.variant
        )

    def acquire_lock(self, lock_wallet, lock_amount, pipeline: WalletPipeline):
        pipeline.new_lock(key=self.group_id, wallet=lock_wallet, amount=lock_amount, reason=WalletPipeline.TRADE)

    objects = models.Manager()
    live_objects = StopLossManager()
    open_objects = StopLossManager(open_only=True)
    not_triggered_objects = StopLossManager(not_triggered_only=True)

    def delete(self, *args, **kwargs):
        self.canceled_at = timezone.now()
        self.save(update_fields=['canceled_at'])
        if self.oco:
            self.oco.cancel_another(self.oco.ORDER, delete_oco=True)

    def hard_delete(self):
        super(StopLoss, self).delete()

    @staticmethod
    def trigger(order, min_price, max_price, matched_trades, pipeline):
        to_cancel_stop_loss = []

        to_trigger_stop_loss_qs = StopLoss.not_triggered_objects.filter(
            Q(side=BUY, trigger_price__lte=max_price) | Q(side=SELL, trigger_price__gte=min_price),
            symbol=order.symbol,
        ).exclude(id=order.stop_loss_id)

        log_prefix = 'MM %s {%s}: ' % (order.symbol.name, order.id)
        logger.info(
            log_prefix + f'to trigger stop loss: {list(to_trigger_stop_loss_qs.values_list("id", flat=True))} {timezone.now()}')

        for stop_loss in to_trigger_stop_loss_qs:
            if stop_loss.oco:
                stop_loss.oco.cancel_another(stop_loss.oco.ORDER)

        for stop_loss in to_trigger_stop_loss_qs:
            from market.utils.order_utils import trigger_stop_loss
            triggered_price = min_price if stop_loss.side == SELL else max_price
            logger.info(
                log_prefix + f'triggering stop loss on {order.symbol} ({stop_loss.id}, {stop_loss.side}) at {triggered_price}, {timezone.now()}')

            # cancel stop loss markets when market triggered orders not fill completely within 1% percent of
            # triggered price
            to_cancel = trigger_stop_loss(pipeline, stop_loss, triggered_price)

            if to_cancel:
                to_cancel_stop_loss.append(to_cancel)
        if to_cancel_stop_loss:
            matched_trades.to_cancel_stoploss = to_cancel_stop_loss

    def __str__(self):
        return f'({self.id}) {self.symbol}-{self.side}'

    class Meta:
        # todo: add constraint filled_amount <= amount
        constraints = [
            CheckConstraint(check=Q(
                amount__gte=0,
                price__gte=0,
                filled_amount__gte=0
            ), name='check_market_stoploss_amounts', ),
        ]
