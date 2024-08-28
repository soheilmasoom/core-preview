import logging
from decimal import Decimal

from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from accounts.authentication import CustomJWTAuthentication

from ledger.models import Wallet
from ledger.models.asset import Asset
from ledger.utils.precision import get_presentation_amount, floor_precision
from ledger.utils.price import get_coins_symbols, get_last_prices
from stake.models import StakeRevenue

logger = logging.getLogger(__name__)


class StakeOverviewAPIView(APIView):
    authentication_classes = (SessionAuthentication, CustomJWTAuthentication)
    permission_classes = (IsAuthenticated,)

    @staticmethod
    def aggregate_revenue_values(asset_revenues, prices):
        total_irt_value = total_usdt_value = Decimal(0)
        for asset_revenue in asset_revenues:
            coin = asset_revenue['symbol']
            price_usdt = prices.get(coin + Asset.USDT, 0)
            price_irt = prices.get(coin + Asset.IRT, 0)

            total_usdt_value += asset_revenue['total_revenue'] * price_usdt
            total_irt_value += asset_revenue['total_revenue'] * price_irt
        return {
            'IRT': get_presentation_amount(floor_precision(total_irt_value)),
            'USDT': get_presentation_amount(floor_precision(total_usdt_value))
        }

    def get(self, request: Request):
        account = request.user.get_account()

        stake_wallets = Wallet.objects.filter(account=account, market=Wallet.STAKE).exclude(balance=0)
        coins = stake_wallets.values_list('asset__symbol', flat=True)
        prices = get_last_prices(get_coins_symbols(coins))

        assets_total_revenues = StakeRevenue.objects.filter(
            stake_request__account=account
        ).values('stake_request__stake_option__asset__symbol').annotate(
            symbol=F('stake_request__stake_option__asset__symbol'),
            total_revenue=Sum('revenue'),
        )

        assets_last_revenues = StakeRevenue.objects.filter(
            created=timezone.now().astimezone().date(),
            stake_request__account=account
        ).values('stake_request__stake_option__asset__symbol', 'created').annotate(
            symbol=F('stake_request__stake_option__asset__symbol'),
            total_revenue=Sum('revenue'),
        )

        from ledger.views import WalletsOverviewAPIView
        return Response({
            'total': WalletsOverviewAPIView.aggregate_wallets_values(
                stake_wallets, prices
            ),
            'total_revenue': self.aggregate_revenue_values(assets_total_revenues, prices),
            'last_revenue': self.aggregate_revenue_values(assets_last_revenues, prices),
        })
