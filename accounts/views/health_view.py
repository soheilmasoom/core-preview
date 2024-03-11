from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.models import NetworkAsset
from ledger.utils.external_price import fetch_external_price, SIDES


class HealthView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        return Response({'status': 'healthy!'})


class PriceHealthView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        symbols = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'GORILLAUSDT']

        missing_prices = []

        errors = {}

        for s in symbols:
            for side in SIDES:
                if fetch_external_price(symbol=s, side=side, allow_stale=False) is None:
                    missing_prices.append(s)

        if missing_prices:
            errors['missing prices'] = missing_prices

        if errors:
            return Response({'status': 'dead', 'errors': errors})
        else:
            return Response({'status': 'healthy!'})
