import logging
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from _base.settings import SYSTEM_ACCOUNT_ID
from accounts.views.jwt_views import DelegatedAccountMixin
from ledger.models import Wallet, DepositAddress, NetworkAsset, Trx
from ledger.models.asset import Asset
from ledger.utils.external_price import BUY, SELL
from ledger.utils.fields import get_irt_market_asset_symbols
from ledger.utils.precision import get_presentation_amount, get_symbol_presentation_price, \
    get_coin_presentation_balance
from ledger.utils.price import get_prices, get_coins_symbols, get_last_prices, get_price
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)


class AssetListSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    balance = serializers.SerializerMethodField()
    balance_irt = serializers.SerializerMethodField()
    balance_usdt = serializers.SerializerMethodField()

    can_deposit = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()

    free = serializers.SerializerMethodField()

    pin_to_top = serializers.SerializerMethodField()

    precision = serializers.SerializerMethodField()

    market_irt_enable = serializers.SerializerMethodField()

    original_name_fa = serializers.SerializerMethodField()
    original_symbol = serializers.SerializerMethodField()

    step_size = serializers.SerializerMethodField()

    def get_market_irt_enable(self, asset: Asset):
        return asset.symbol in self.context['enable_irt_market_list']

    def get_precision(self, asset: Asset):
        return asset.get_precision()

    def get_pin_to_top(self, asset: Asset):
        return asset.pin_to_top

    def get_wallet(self, asset: Asset):
        return self.context['asset_to_wallet'].get(asset.id)

    def get_debt(self, asset: Asset) -> Decimal:
        debt = self.context['asset_to_debt_wallet'].get(asset.id)
        if debt:
            return debt.balance
        else:
            return Decimal()

    def get_balance(self, asset: Asset):
        wallet = self.get_wallet(asset)

        if not wallet:
            return '0'

        return get_coin_presentation_balance(asset.symbol, wallet.balance + self.get_debt(asset))

    def get_balance_irt(self, asset: Asset):
        balance = Decimal(self.get_balance(asset))

        if not balance:
            return 0

        price = self._get_last_price_irt(asset.symbol)
        if not price:
            return

        return get_symbol_presentation_price(asset.symbol + 'IRT', balance * price, trunc_zero=True)

    def _get_price_irt(self, coin: str):
        return self.context['prices'].get(coin + Asset.IRT)

    def _get_price_usdt(self, coin: str):
        return self.context['prices'].get(coin + Asset.USDT)

    def _get_last_price_irt(self, coin: str):
        return self.context['last_prices'].get(coin + Asset.IRT)

    def _get_last_price_usdt(self, coin: str):
        return self.context['last_prices'].get(coin + Asset.USDT)

    def get_balance_usdt(self, asset: Asset):
        balance = Decimal(self.get_balance(asset))

        if not balance:
            return 0

        price = self._get_last_price_usdt(asset.symbol)
        if not price:
            return

        return get_symbol_presentation_price(asset.symbol + 'USDT', balance * price, trunc_zero=True)

    def get_free(self, asset: Asset):
        wallet = self.get_wallet(asset)

        if not wallet:
            return '0'

        free = max(Decimal(), wallet.get_free() + self.get_debt(asset))
        return get_coin_presentation_balance(asset.symbol, free)

    def get_can_deposit(self, asset: Asset):
        return asset.symbol in self.context['deposit_enable_coins']

    def get_can_withdraw(self, asset: Asset):
        return asset.symbol in self.context['withdraw_enable_coins']

    def get_logo(self, asset: Asset):
        return settings.MINIO_STORAGE_STATIC_URL + '/coins/%s.png' % asset.symbol

    def get_original_symbol(self, asset: Asset):
        return asset.get_original_symbol()

    def get_original_name_fa(self, asset: Asset):
        return asset.original_name_fa or asset.name_fa

    def get_step_size(self, asset: Asset):
        return Asset.PRECISION

    class Meta:
        model = Asset
        fields = ('symbol', 'precision', 'free', 'balance', 'balance_irt', 'balance_usdt',
                  'can_deposit', 'can_withdraw', 'trade_enable', 'pin_to_top', 'market_irt_enable',
                  'name', 'name_fa', 'logo', 'original_symbol', 'original_name_fa', 'step_size',)

        ref_name = 'ledger asset'


class NetworkAssetSerializer(serializers.ModelSerializer):
    network = serializers.CharField(source='network.symbol')
    network_name = serializers.CharField(source='network.name')
    address = serializers.SerializerMethodField()
    memo = serializers.SerializerMethodField()
    can_deposit = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()
    address_regex = serializers.CharField(source='network.address_regex')
    slow_withdraw = serializers.BooleanField(source='network.slow_withdraw')

    withdraw_commission = serializers.SerializerMethodField()
    min_withdraw = serializers.SerializerMethodField()
    min_confirm = serializers.IntegerField(source='network.min_confirm')
    min_deposit = serializers.SerializerMethodField()

    withdraw_precision = serializers.SerializerMethodField()

    need_memo = serializers.BooleanField(source='network.need_memo')

    def get_can_deposit(self, network_asset: NetworkAsset):
        return network_asset.can_deposit_enabled()

    def get_can_withdraw(self, network_asset: NetworkAsset):
        return network_asset.can_withdraw_enabled()

    def get_address(self, network_asset: NetworkAsset):
        addresses = self.context.get('addresses', {})
        address_data = addresses.get(network_asset.network.symbol)
        return address_data and address_data[0]

    def get_memo(self, network_asset: NetworkAsset):
        addresses = self.context.get('addresses', {})
        address_data = addresses.get(network_asset.network.symbol)
        return address_data and address_data[1]

    def get_min_withdraw(self, network_asset: NetworkAsset):
        return get_presentation_amount(max(network_asset.withdraw_min, network_asset.withdraw_fee))

    def get_min_deposit(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.get_min_deposit())

    def get_withdraw_commission(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.withdraw_fee)

    def get_withdraw_precision(self, network_asset: NetworkAsset):
        return network_asset.withdraw_precision

    class Meta:
        fields = ('network', 'address', 'memo', 'can_deposit', 'can_withdraw', 'withdraw_commission', 'min_withdraw',
                  'min_deposit', 'network_name', 'address_regex', 'withdraw_precision', 'need_memo', 'min_confirm',
                  'slow_withdraw')
        model = NetworkAsset


class AssetRetrieveSerializer(AssetListSerializer):
    networks = serializers.SerializerMethodField()

    def get_networks(self, asset: Asset):
        network_assets = asset.networkasset_set.all().prefetch_related('network', 'asset').order_by('withdraw_fee')

        account = self.context['request'].user.get_account()

        deposit_addresses = DepositAddress.objects.filter(
            address_key__account=account,
            address_key__deleted=False
        ).prefetch_related('address_key')

        address_mapping = {
            deposit.network.symbol: (deposit.address, deposit.address_key.memo) for deposit in deposit_addresses
        }

        serializer = NetworkAssetSerializer(network_assets, many=True, context={
            'addresses': address_mapping,
        })

        return serializer.data

    class Meta(AssetListSerializer.Meta):
        fields = (*AssetListSerializer.Meta.fields, 'networks')


class WalletViewSet(ModelViewSet, DelegatedAccountMixin):

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        account, variant = self.get_account_variant(self.request)
        wallets = Wallet.objects.filter(account=account, market=Wallet.SPOT, variant=variant)
        debt_wallets = Wallet.objects.filter(account=account, market=Wallet.DEBT, variant=variant)
        ctx['asset_to_wallet'] = {wallet.asset_id: wallet for wallet in wallets}
        ctx['asset_to_debt_wallet'] = {wallet.asset_id: wallet for wallet in debt_wallets}
        ctx['enable_irt_market_list'] = get_irt_market_asset_symbols()

        if self.action == 'list':
            coins = list(self.get_queryset().values_list('symbol', flat=True))
        else:
            coins = [self.get_object().symbol]

        symbols = get_coins_symbols(coins)
        ctx['prices'] = get_prices(symbols, side=SELL, allow_stale=True)
        ctx['last_prices'] = get_last_prices(symbols)

        withdraw_enable_coins = set(NetworkAsset.objects.filter(
            asset__symbol__in=coins,
            network__can_withdraw=True,
            hedger_withdraw_enable=True,
            can_withdraw=True,
        ).values_list('asset__symbol', flat=True)) | {'IRT'}

        ctx['withdraw_enable_coins'] = withdraw_enable_coins

        deposit_enable_coins = set(NetworkAsset.objects.filter(
            asset__symbol__in=coins,
            network__can_deposit=True,
            hedger_deposit_enable=True,
            can_deposit=True,
        ).values_list('asset__symbol', flat=True)) | {'IRT'}

        ctx['deposit_enable_coins'] = deposit_enable_coins

        return ctx

    def get_serializer_class(self):
        if self.action == 'list':
            return AssetListSerializer
        else:
            return AssetRetrieveSerializer

    def get_object(self):
        return get_object_or_404(Asset, symbol=self.kwargs['symbol'].upper())

    def get_queryset(self):
        account = self.request.user.get_account()

        disabled_assets = Wallet.objects.filter(
            account=account,
            asset__enable=False
        ).exclude(balance=0).values_list('asset_id', flat=True)

        assets = Asset.objects.filter(Q(enable=True) | Q(id__in=disabled_assets))

        only_coin = self.request.query_params.get('coin') == '1'
        if only_coin:
            assets = assets.exclude(symbol=Asset.IRT)

        can_deposit = self.request.query_params.get('can_deposit') == '1'
        if can_deposit:
            assets = assets.filter(
                networkasset__can_deposit=True,
                networkasset__network__can_deposit=True
            ).distinct()

        can_withdraw = self.request.query_params.get('can_withdraw') == '1'
        if can_withdraw:
            assets = assets.filter(
                networkasset__can_withdraw=True,
                networkasset__network__can_withdraw=True
            ).distinct()

        has_balance = self.request.query_params.get('has_balance') == '1'
        if has_balance:
            asset_ids = Wallet.objects.filter(
                market=Wallet.SPOT,
                account=account,
                balance__gt=0
            ).values_list('asset_id', flat=True)

            assets = assets.filter(id__in=asset_ids)

        return assets

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data

        pin_to_top_wallets = list(filter(lambda w: w['pin_to_top'], data))
        with_balance_wallets = list(filter(lambda w: w['balance'] != '0' and not w['pin_to_top'], data))
        without_balance_wallets = list(filter(lambda w: w['balance'] == '0' and not w['pin_to_top'], data))

        wallets = pin_to_top_wallets + sorted(
            with_balance_wallets,
            key=lambda w: Decimal(w['balance_irt'] or 0),
            reverse=True
        ) + without_balance_wallets

        return Response(wallets)


class WalletBalanceView(APIView, DelegatedAccountMixin):
    def get(self, request, *args, **kwargs):
        market = request.query_params.get('market', Wallet.SPOT)
        asset = get_object_or_404(Asset, symbol=kwargs['symbol'].upper())
        account, variant = self.get_account_variant(self.request)
        wallet = asset.get_wallet(account, market=market, variant=variant)

        free = wallet.get_free() + wallet.credit

        if market == Wallet.SPOT:
            debt_wallet = Wallet.objects.filter(
               asset=asset,
               account=account,
               market=Wallet.DEBT,
               variant__isnull=True
            ).first()

            if debt_wallet:
                free = max(Decimal(), free + debt_wallet.balance)

        if asset.symbol == Asset.IRT:
            free = int(free)

        return Response({
            'symbol': asset.symbol,  # todo: for backward compatability for application
            'asset': asset.symbol,
            'balance': get_presentation_amount(free),
        })


class BriefNetworkAssetsSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    symbol = serializers.SerializerMethodField()
    address_regex = serializers.SerializerMethodField()

    def get_name(self, network_asset: NetworkAsset):
        return network_asset.network.name

    def get_symbol(self, network_asset: NetworkAsset):
        return network_asset.network.symbol

    def get_address_regex(self, network_asset: NetworkAsset):
        return network_asset.network.address_regex

    class Meta:
        fields = ('name', 'symbol', 'address_regex')
        model = NetworkAsset


class BriefNetworkAssetsView(ListAPIView):
    serializer_class = BriefNetworkAssetsSerializer

    def get_queryset(self):
        query_params = self.request.query_params
        query_set = NetworkAsset.objects.all()
        if 'symbol' in query_params:
            return query_set.filter(asset__symbol=query_params['symbol'].upper(),
                                    can_withdraw=True,
                                    network__can_withdraw=True,
                                    hedger_withdraw_enable=True)
        else:
            query_set = query_set.distinct('network__symbol')

        return query_set.filter(can_withdraw=True, network__can_withdraw=True, network__is_universal=True)


class WalletSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    free = serializers.SerializerMethodField()

    def get_asset(self, wallet: Wallet):
        return wallet.asset.symbol

    def get_free(self, wallet: Wallet):
        return wallet.get_free()

    class Meta:
        model = Wallet
        fields = ('asset', 'free', 'balance', 'locked')


class ConvertDustView(APIView):

    def post(self, *args):
        account = self.request.user.get_account()
        irt_asset = Asset.get(Asset.IRT)

        spot_wallets = list(Wallet.objects.filter(
            account=account,
            market=Wallet.SPOT,
            balance__gt=0,
            variant__isnull=True
        ).exclude(asset=irt_asset).prefetch_related('asset'))

        group_id = uuid4()
        irt_amount = 0

        any_converted = False

        with WalletPipeline() as pipeline:
            for wallet in spot_wallets:
                price = get_price(
                    wallet.asset.symbol + Asset.IRT,
                    side=BUY,
                )

                if price is None:
                    continue

                free = wallet.get_free()
                free_irt_value = free * price

                if Decimal(0) < free_irt_value < Decimal('10000'):
                    logger.info('Converting dust %s' % wallet)

                    pipeline.new_trx(
                        sender=wallet,
                        receiver=wallet.asset.get_wallet(SYSTEM_ACCOUNT_ID),
                        amount=free,
                        group_id=group_id,
                        scope=Trx.DUST
                    )

                    irt_amount += price * free

                    any_converted = True

            pipeline.new_trx(
                sender=irt_asset.get_wallet(SYSTEM_ACCOUNT_ID),
                receiver=irt_asset.get_wallet(account),
                amount=irt_amount,
                group_id=group_id,
                scope=Trx.DUST,
            )

        if not any_converted:
            raise ValidationError('هیچ گزینه‌ای برای تبدیل خرد وجود ندارد.')

        return Response({'msg': 'convert_dust success'}, status=status.HTTP_200_OK)
