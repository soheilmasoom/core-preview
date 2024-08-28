from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.authentication import CustomJWTAuthentication, CustomTokenAuthentication
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from ledger.models import Wallet
from ledger.views.wallet_view import WalletSerializer


class BalanceInfoView(ListAPIView):
    authentication_classes = (SessionAuthentication, CustomTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    serializer_class = WalletSerializer

    def get_queryset(self):
        return Wallet.objects.filter(
            account=self.request.user.get_account(),
            market=Wallet.SPOT,
            variant__isnull=True
        ).prefetch_related('asset')
