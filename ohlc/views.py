from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .models import Candle, MaterializedCandle


class ChartViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def line_chart(self, request):
        symbol = request.query_params.get('symbol')
        timeframe = request.query_params.get('type', 'daily')

        if not symbol:
            return Response({"error": "Symbol parameter is required"}, status=400)

        # Try to get from cache first
        cache_key = f"chart_{symbol}_{timeframe}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        now = timezone.now()
        timeframe_mapping = {
            'yearly': {'days': 365, 'model': MaterializedCandle, 'frame': '1d', 'cache_time': 0 * 6 * 60 * 60}, # 6 hour
            'monthly': {'days': 30, 'model': MaterializedCandle, 'frame': '4h', 'cache_time': 0 * 120 * 60},    # 2 hours
            'weekly': {'days': 7, 'model': MaterializedCandle, 'frame': '1h', 'cache_time': 0 * 30 * 60},
            'daily': {'days': 1, 'model': MaterializedCandle, 'frame': '1h', 'cache_time': 0 * 30 * 60},
            'hourly': {'days': 1 / 24, 'model': Candle, 'frame': None, 'cache_time': 60}
        }

        if timeframe not in timeframe_mapping:
            return Response({"error": "Invalid timeframe"}, status=400)

        mapping = timeframe_mapping[timeframe]
        start_time = now - timedelta(days=mapping['days'])
        Model = mapping['model']

        if Model == MaterializedCandle:
            candles = Model.objects.filter(
                symbol=symbol,
                timestamp__gte=start_time,
                timeframe=mapping['frame']
            ).order_by('timestamp')
        else:
            candles = Model.objects.filter(
                symbol=symbol,
                timestamp__gte=start_time
            ).order_by('timestamp')

        data = list(candles.values('timestamp', 'close'))

        cache.set(cache_key, data, mapping['cache_time'])

        return Response(data)
