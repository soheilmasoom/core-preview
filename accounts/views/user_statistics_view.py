from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum

from rest_framework.views import APIView
from rest_framework.response import Response

from accounts.models import LevelGrants
from accounting.models import TradeRevenue
from financial.utils.withdraw_limit import get_crypto_withdraw_irt_value, get_fiat_withdraw_irt_value


class UserStatisticsView(APIView):
    def get(self, request):
        user = request.user
        account = user.get_account()
        all_trades_irt = account.trade_volume_irt
        last_30d_trades_irt = TradeRevenue.objects.filter(
            account=account,
            created__gte=timezone.now() - timedelta(days=30)
        ).aggregate(total=Sum('value_irt'))['total'] or 0

        current_day_fiat_withdraw = get_fiat_withdraw_irt_value(user)
        current_day_crypto_withdraw = get_crypto_withdraw_irt_value(user)

        return Response(
            {
                'all_trades_irt': all_trades_irt,
                'last_30d_trades_irt': last_30d_trades_irt,
                'daily_fiat_withdraw_limit': LevelGrants.get_max_daily_fiat_withdraw(user),
                'daily_crypto_withdraw_limit': LevelGrants.get_max_daily_crypto_withdraw(user),
                'current_day_fiat_withdraw': current_day_fiat_withdraw,
                'current_day_crypto_withdraw': current_day_crypto_withdraw
            }
        )
