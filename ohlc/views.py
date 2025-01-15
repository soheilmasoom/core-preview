from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from datetime import timedelta
from .models import Candle, MaterializedCandle


class ChartViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def line_chart(self, request):
        symbol = request.query_params.get('symbol')
        timeframe = request.query_params.get('type', 'daily')

        if not symbol:
            return Response({"error": "Symbol parameter is required"}, status=400)

        now = timezone.now()
        timeframe_mapping = {
            'yearly': {'days': 365, 'model': MaterializedCandle, 'frame': '1d'},
            'monthly': {'days': 30, 'model': MaterializedCandle, 'frame': '4h'},
            'weekly': {'days': 7, 'model': MaterializedCandle, 'frame': '1h'},
            'daily': {'days': 1, 'model': MaterializedCandle, 'frame': '15min'},
            'hourly': {'days': 1 / 24, 'model': Candle, 'frame': None}
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

        data = list(candles.values('timestamp', 'close'))  # Only timestamp and close price
        return Response(data)
