import logging
from decimal import Decimal

from django.db.models import F
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.throttle import BursAPIRateThrottle
from ledger.utils.external_price import BUY, SELL
from ledger.utils.precision import floor_precision
from market.models import PairSymbol, Order, Trade

logger = logging.getLogger(__name__)


class OrderBookAPIView(APIView):
    permission_classes = ()
    throttle_classes = [BursAPIRateThrottle]

    def get(self, request, symbol):
        symbol = get_object_or_404(PairSymbol, name=symbol.upper(), enable=True)
        open_orders = Order.open_objects.filter(symbol=symbol).annotate(
            unfilled_amount=F('amount') - F('filled_amount')
        ).exclude(unfilled_amount=0).values('side', 'price', 'unfilled_amount')

        open_orders = Order.quantize_values(symbol, open_orders)

        bids = Order.get_formatted_orders(open_orders, symbol, BUY)
        asks = Order.get_formatted_orders(open_orders, symbol, SELL)

        top_ask = Decimal(asks[0]['price']) if asks else Decimal('inf')

        filtered_bids = list(filter(lambda o: Decimal(o['price']) < top_ask if asks else True, bids))

        if len(filtered_bids) < len(bids):
            logger.critical(f'There are unmatched orders in {symbol} order book', extra={
                'symbol': str(symbol),
                'bids': bids,
                'asks': asks,
            })

        last_trade = Trade.get_last(symbol=symbol)

        results = {
            'last_trade': last_trade.format_values() if last_trade else {'amount': None, 'price': None, 'total': None},
            'bids': filtered_bids[:20],
            'asks': asks[:20],
        }

        if not request.auth and request.user and not request.user.is_anonymous:
            open_orders = {
                (order['side'], str(floor_precision(order['price'], symbol.tick_size))): True for order in
                Order.open_objects.filter(
                    symbol=symbol, account=self.request.user.get_account()
                ).values('side', 'price')
            }
            for side in (BUY, SELL):
                key = 'bids' if side == BUY else 'asks'
                results[key] = [
                    {**order, 'user_order': open_orders.get((side, order['price']), False)} for order in results[key]
                ]
        return Response(results, status=status.HTTP_200_OK)
