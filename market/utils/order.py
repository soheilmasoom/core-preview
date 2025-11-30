from decimal import Decimal

from django.db.models import F, Sum

from ledger.utils.precision import floor_precision
from market.models import Order, Trade


def get_filled_price(order: Order):
    fills_amount, fills_value = Trade.objects.filter(order_id=order.id).annotate(
        value=F('amount') * F('price')).aggregate(sum_amount=Sum('amount'), sum_value=Sum('value')).values()
    amount = Decimal((fills_amount or 0))
    if not amount:
        return None
    price = Decimal((fills_value or 0)) / amount
    return floor_precision(price, order.symbol.tick_size)
