from decimal import Decimal

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .models import Ohlc1D, Ohlc1H


class ChartViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def line_chart(self, request):
        symbol = request.query_params.get('symbol')
        timeframe = request.query_params.get('type', 'daily')

        if not symbol:
            return Response({"error": "Symbol parameter is required"}, status=400)

        cache_key = f"chart_{symbol}_{timeframe}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        now = timezone.now()
        timeframe_mapping = {
            'yearly': {'days': 365, 'model': Ohlc1D, 'cache_time': 12 * 60 * 60},
            'monthly': {'days': 30, 'model': Ohlc1H, 'cache_time': 4 * 60 * 60},
            'weekly': {'days': 7, 'model': Ohlc1H, 'cache_time': 30 * 60},
            'daily': {'days': 1, 'model': Ohlc1H, 'cache_time': 30 * 60},
        }

        if timeframe not in timeframe_mapping:
            return Response({"error": "Invalid timeframe"}, status=400)

        mapping = timeframe_mapping[timeframe]
        Model = mapping['model']

        if 'days' in mapping:
            start_time = now - timedelta(days=mapping['days'])
        else:
            return Response({"error": "Invalid timeframe configuration"}, status=500)

        candles = Model.objects.filter(
            symbol=symbol,
            timestamp__gte=start_time
        ).exclude(close=Decimal('0')).order_by('timestamp')

        # Fetch timestamp and close price
        data = list(candles.values('timestamp', 'close'))

        cache.set(cache_key, data, mapping['cache_time'])

        return Response(data)
