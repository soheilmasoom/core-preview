import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.db.models import F, CheckConstraint, Q, Sum, Max, Min
from django.utils import timezone

from ledger.utils.external_price import BUY
from ledger.utils.fields import get_group_id_field
from ledger.utils.precision import floor_precision, decimal_to_str
from ledger.utils.revert import revert_trx_group_via_revert_helper
from market.models import BaseTrade

logger = logging.getLogger(__name__)


class Trade(BaseTrade):
    SYSTEM, SYSTEM_MAKER, SYSTEM_TAKER, MARKET = 'system', 'sys-make', 'sys-take', 'market'
    SOURCE_CHOICES = (MARKET, 'market'), (SYSTEM, 'system'), (SYSTEM_MAKER, SYSTEM_MAKER), \
                     (SYSTEM_TAKER, SYSTEM_TAKER)

    DONE, REVERT = 'd', 'r'
    STATUS_CHOICES = (DONE, 'done'), (REVERT, 'revert')

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=DONE, db_index=True)

    group_id = get_group_id_field(db_index=True)

    order_id = models.PositiveIntegerField(db_index=True)

    trade_source = models.CharField(
        max_length=8,
        choices=SOURCE_CHOICES,
        db_index=True,
        default=MARKET
    )
    position = models.ForeignKey(to='ledger.MarginPosition', on_delete=models.CASCADE, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['created']),
            models.Index(fields=['account', 'symbol']),
            models.Index(fields=['symbol', 'side', 'created']),
        ]
        constraints = [
            CheckConstraint(check=Q(
                amount__gte=0,
                price__gte=0,
                fee_amount__gte=0,
            ), name='check_market_trade_amounts', ),
        ]

        permissions = [
            ("list_trade", "Can list trade"),
        ]

    def __str__(self):
        return f'{self.symbol}-{self.side} ' \
               f'[p:{self.price:.2f}] (a:{self.amount:.5f})'

    @classmethod
    def get_last(cls, symbol, max_datetime=None):
        qs = cls.objects.filter(symbol=symbol).order_by('-id')
        if max_datetime:
            qs = qs.filter(created__lte=max_datetime)
        return qs.first()

    def format_values(self):
        return {
            'amount': decimal_to_str(floor_precision(self.amount, self.symbol.step_size)),
            'price': decimal_to_str(floor_precision(self.price, self.symbol.tick_size)),
            'total': decimal_to_str(floor_precision(self.amount * self.price, self.symbol.tick_size)),
        }

    @classmethod
    def get_grouped_by_count(cls, symbol_id: int, interval_in_secs: int, start: datetime, end: datetime,
                             count_back=None):
        results = Trade.get_grouped_by_interval(symbol_id, interval_in_secs, start, end)
        if not count_back:
            return results
        # TODO: clean it later.
        try_count = 0
        while try_count < 3 and len(results) < count_back:
            try_count += 1
            shift = (end - start) * try_count
            older_results = Trade.get_grouped_by_interval(symbol_id, interval_in_secs, start - shift, end - shift)
            results = older_results[(len(results)) - count_back:] + results
        return results

    @classmethod
    def get_grouped_by_interval(cls, symbol_id: int, interval_in_secs: int, start: datetime, end: datetime):
        from market.utils.datetime_utils import ceil_date, floor_date
        if interval_in_secs <= 3600:
            round_func = ceil_date
            tf_shift = '30 min'
        else:
            round_func = floor_date
            tf_shift = '0 sec'
        start = round_func(start, seconds=interval_in_secs)
        end = round_func(end, seconds=interval_in_secs)
        return [
            {'timestamp': group.tf, 'open': group.open[1], 'high': group.high, 'low': group.low,
             'close': group.close[1], 'volume': group.volume}
            for group in cls.objects.raw(
                "select min(id) as id, "
                "min(array[id, price]) as open, max(array[id, price]) as close, "
                "max(price) as high, min(price) as low, "
                "sum(amount) as volume, "
                "(date_trunc('seconds', (created - (timestamptz 'epoch' - interval %s)) / %s) * %s + (timestamptz 'epoch' - interval %s)) as tf "
                "from market_trade where symbol_id = %s and side = 'buy' and status = 'd' and created between %s and %s group by tf order by tf",
                [tf_shift, interval_in_secs, interval_in_secs, tf_shift, symbol_id, start, end]
            )
        ]

    @staticmethod
    def get_interval_top_prices(symbol_ids=None, min_datetime=None):
        min_datetime = min_datetime or (timezone.now() - timedelta(seconds=5))
        market_top_prices = defaultdict(lambda: Decimal())
        symbol_filter = {'symbol_id__in': symbol_ids} if symbol_ids else {}
        for depth in Trade.objects.filter(**symbol_filter, created__gte=min_datetime).values('symbol', 'side').annotate(
                max_price=Max('price'), min_price=Min('price')):
            market_top_prices[
                (depth['symbol'], depth['side'])
            ] = (depth['max_price'] if depth['side'] == BUY else depth['min_price']) or Decimal()
        return market_top_prices

    @staticmethod
    def get_account_orders_filled_price(account_id, order_filter=None):
        extra_filter = {}
        if order_filter:
            from market.models import Order
            order_ids = list(Order.objects.filter(account_id=account_id, **order_filter).values_list('id', flat=True))
            if not order_ids:
                return {}
            extra_filter = {
                'order_id__in': order_ids
            }
        return {
            trade['order_id']: (trade['sum_amount'], trade['sum_value']) for trade in
            Trade.objects.filter(account=account_id, **extra_filter).annotate(
                value=F('amount') * F('price')
            ).values('order_id').annotate(sum_amount=Sum('amount'), sum_value=Sum('value')).values(
                'order_id', 'sum_amount', 'sum_value'
            )
        }

    @classmethod
    def get_top_prices(cls, symbol_id):
        from market.utils.redis import get_top_prices
        top_prices = get_top_prices(symbol_id, scope='stoploss')
        if not top_prices:
            top_prices = defaultdict(lambda: Decimal())
            for k, v in Trade.get_interval_top_prices([symbol_id]).items():
                top_prices[k[1]] = v
        return top_prices

    def revert(self):
        from ledger.utils.wallet_pipeline import WalletPipeline

        with WalletPipeline() as pipeline:
            self.status = self.REVERT
            self.save(update_fields=['status'])
            revert_trx_group_via_revert_helper(pipeline, self.account, self.group_id)
