from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers
from rest_framework.generics import ListAPIView

from ledger.models import Wallet, Asset
from ledger.utils.precision import get_presentation_amount
from ledger.utils.price import get_coins_symbols, get_last_prices
from stake.models import StakeOption, StakeRevenue, StakeRequest
from stake.views.stake_option_view import StakeOptionSerializer


class StakeWalletSerializer(StakeOptionSerializer):
    balance = serializers.SerializerMethodField()
    balance_value_irt = serializers.SerializerMethodField()
    balance_value_usdt = serializers.SerializerMethodField()
    revenue = serializers.SerializerMethodField()
    revenue_irt = serializers.SerializerMethodField()
    revenue_usdt = serializers.SerializerMethodField()

    def get_price_irt(self, asset):
        return self.context['prices'].get(asset + Asset.IRT, 0)

    def get_price_usdt(self, asset):
        return self.context['prices'].get(asset + Asset.USDT, 0)

    def get_balance(self, stake_option: StakeOption):
        return get_presentation_amount(self.context['stake_wallets'].get(stake_option.asset.symbol) or Decimal(0))

    def get_balance_value_irt(self, stake_option: StakeOption):
        balance = self.context['stake_wallets'].get(stake_option.asset.symbol) or 0
        price = self.get_price_irt(stake_option.asset.symbol)
        return get_presentation_amount(balance * price)

    def get_balance_value_usdt(self, stake_option: StakeOption):
        balance = self.context['stake_wallets'].get(stake_option.asset.symbol) or 0
        price = self.get_price_usdt(stake_option.asset.symbol)
        return get_presentation_amount(balance * price)

    def get_revenue(self, stake_option: StakeOption):
        return get_presentation_amount(self.context['stake_revenues'].get(stake_option.id) or Decimal(0))

    def get_revenue_irt(self, stake_option: StakeOption):
        revenue = self.context['stake_revenues'].get(stake_option.id) or 0
        price = self.get_price_irt(stake_option.asset.symbol)
        return get_presentation_amount(revenue * price)

    def get_revenue_usdt(self, stake_option: StakeOption):
        revenue = self.context['stake_revenues'].get(stake_option.id) or 0
        price = self.get_price_usdt(stake_option.asset.symbol)
        return get_presentation_amount(revenue * price)

    class Meta:
        model = StakeOption
        fields = ('id', 'asset', 'balance', 'balance_value_irt', 'balance_value_usdt', 'revenue',
                  'revenue_irt', 'revenue_usdt')


class StakeWalletsAPIView(ListAPIView):
    serializer_class = StakeWalletSerializer

    def get_queryset(self):
        return StakeOption.objects.filter(stakerequest__in=self.get_active_requests(),).distinct()

    def get_active_requests(self):
        active_requests = StakeRequest.objects.filter(
            account=self.request.user.get_account()
        ).exclude(
            status__in=(StakeRequest.FINISHED, StakeRequest.CANCEL_COMPLETE)
        ).values_list('id', flat=True)
        return active_requests

    def get_serializer_context(self):
        account = self.request.user.get_account()
        ctx = super(StakeWalletsAPIView, self).get_serializer_context()
        queryset = self.get_queryset()
        coins = queryset.values_list('asset__symbol', flat=True)
        ctx['prices'] = get_last_prices(get_coins_symbols(coins))
        ctx['stake_wallets'] = {
            coin: Asset.get(coin).get_wallet(account, Wallet.STAKE).balance for coin in coins
        }
        ctx['stake_revenues'] = {
            revenue['stake_request__stake_option']: revenue['total_revenue'] for revenue in StakeRevenue.objects.filter(
                stake_request__in=self.get_active_requests()
            ).values('stake_request__stake_option').annotate(total_revenue=Sum('revenue'))
        }
        return ctx
