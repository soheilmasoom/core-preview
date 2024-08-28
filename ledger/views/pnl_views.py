from datetime import timedelta

from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from accounts.authentication import CustomJWTAuthentication

from ledger.models import PNLHistory, Wallet
from ledger.utils.precision import floor_precision


class PNLOverview(APIView):
    authentication_classes = (SessionAuthentication, CustomJWTAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request):
        market = self.request.query_params.get('market')
        if not market or market not in (Wallet.SPOT, Wallet.MARGIN):
            raise ValidationError(_('valid market is required'))
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        profit_info = PNLHistory.objects.filter(
            account=self.request.user.get_account(), date__gt=today - timedelta(days=30), market=market
        ).values('base_asset').annotate(
            cumulative_profit_30=Sum('profit'),
            cumulative_profit_7=Sum('profit', filter=Q(date__gt=today - timedelta(days=7))),
            last_profit=Sum('profit', filter=Q(date__gte=today))
        )

        asset_roundness = {
            'IRT': 0,
            'USDT': 2,
        }

        return Response({
            pnl['base_asset']: {
                '1': floor_precision(pnl['last_profit'], asset_roundness[pnl['base_asset']]) if pnl[
                    'last_profit'] else None,
                '7': floor_precision(pnl['cumulative_profit_7'], asset_roundness[pnl['base_asset']]) if pnl[
                    'cumulative_profit_7'] else None,
                '30': floor_precision(pnl['cumulative_profit_30'], asset_roundness[pnl['base_asset']]) if pnl[
                    'cumulative_profit_30'] else None,
            } for pnl in profit_info
        })
