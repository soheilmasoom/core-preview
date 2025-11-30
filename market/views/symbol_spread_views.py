from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CustomTokenAuthentication
from ledger.utils.external_price import SELL, BUY
from ledger.utils.otc import get_otc_spread
from market.models import PairSymbol


class SymbolSpreadListView(APIView):
    authentication_classes = (CustomTokenAuthentication, )

    def get(self, request):

        spreads = []

        for symbol in PairSymbol.objects.filter(enable=True):
            ask_spread = get_otc_spread(coin=symbol.asset.symbol, base_coin=symbol.base_asset.symbol, side=SELL)
            bid_spread = get_otc_spread(coin=symbol.asset.symbol, base_coin=symbol.base_asset.symbol, side=BUY)

            spreads.append({
                'name': symbol.name,
                'ask_spread': ask_spread,
                'bid_spread': bid_spread,
            })

        return Response(spreads)
