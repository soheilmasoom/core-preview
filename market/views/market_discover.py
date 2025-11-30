from rest_framework.views import APIView
from rest_framework.response import Response

from market.utils.trade import get_markets_info

from ledger.models import Asset


class MarketDiscoverView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        base = request.query_params.get('base', 'USDT')

        if base not in [Asset.IRT, Asset.USDT]:
            return Response({'Error': 'Invalid market base'}, status=404)

        markets_info = {
            'base': base,
            'info': get_markets_info(base)
        }

        return Response(markets_info)
