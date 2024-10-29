from decimal import Decimal

from django.db.models import F, Sum, Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from ledger.models import Wallet, MarginPosition
from ledger.models.asset import Asset, AssetSerializerMini
from ledger.utils.external_price import SELL, LONG
from ledger.utils.precision import get_presentation_amount, get_margin_coin_presentation_balance, \
    get_coin_presentation_balance
from ledger.utils.precision import get_symbol_presentation_price
from ledger.utils.price import get_last_price
from market.models import PairSymbol


class MarginAssetListSerializer(AssetSerializerMini):
    balance = serializers.SerializerMethodField()
    balance_usdt = serializers.SerializerMethodField()
    free = serializers.SerializerMethodField()
    borrowed = serializers.SerializerMethodField()
    equity = serializers.SerializerMethodField()

    def get_wallet(self, asset: Asset):
        return self.context['asset_to_wallet'].get(asset.id)

    def get_loan_wallet(self, asset: Asset):
        return self.context['asset_to_loan'].get(asset.id)

    def get_balance(self, asset: Asset):
        wallet = self.get_wallet(asset)

        if not wallet:
            return '0'

        return wallet.balance

    def get_balance_usdt(self, asset: Asset):
        wallet = self.get_wallet(asset)

        if not wallet:
            return '0'

        price = get_last_price(wallet.asset.symbol + Asset.USDT)
        amount = wallet.balance * price

        return get_symbol_presentation_price(asset.symbol + 'USDT', amount)

    def get_free(self, asset: Asset):
        wallet = self.get_wallet(asset)

        if not wallet:
            return '0'

        return wallet.get_free()

    def get_borrowed(self, asset: Asset):
        loan = self.get_loan_wallet(asset)

        if not loan:
            return '0'

        return -loan.balance

    def get_equity(self, asset: Asset):
        wallet = self.get_wallet(asset)
        loan = self.get_loan_wallet(asset)

        if wallet:
            wallet_value = wallet.balance
        else:
            wallet_value = 0

        if loan:
            loan_value = loan.balance
        else:
            loan_value = 0

        return loan_value + wallet_value

    class Meta:
        model = Asset
        fields = (*AssetSerializerMini.Meta.fields, 'free', 'balance', 'balance_usdt', 'borrowed', 'equity')
        ref_name = 'margin wallets'


class MarginWalletViewSet(ModelViewSet):
    serializer_class = MarginAssetListSerializer
    queryset = Asset.live_objects.filter(Q(pair__margin_enable=True) | Q(trading_pair__margin_enable=True)).distinct()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()

        account = self.request.user.get_account()
        wallets = Wallet.objects.filter(account=account, market=Wallet.MARGIN, variant__isnull=True)
        loans = Wallet.objects.filter(account=account, market=Wallet.LOAN)

        ctx['asset_to_wallet'] = {wallet.asset_id: wallet for wallet in wallets}
        ctx['asset_to_loan'] = {wallet.asset_id: wallet for wallet in loans}

        return ctx


class MarginAssetSerializer(AssetSerializerMini):
    margin_position = serializers.SerializerMethodField()
    available_margin = serializers.SerializerMethodField()
    equity = serializers.SerializerMethodField()
    locked_amount = serializers.SerializerMethodField()
    pnl = serializers.SerializerMethodField()

    def get_asset(self, asset: Asset):
        return self.context.get(asset.symbol)

    def get_margin_position(self, asset: Asset):
        asset_data = self.get_asset(asset)

        return get_margin_coin_presentation_balance(asset.symbol, Decimal(asset_data.get('equity', 0)))

    def get_available_margin(self, asset: Asset):
        cross_wallet = self.get_asset(asset).get('cross_wallet')

        if not cross_wallet:
            return Decimal('0')

        return get_margin_coin_presentation_balance(asset.symbol, cross_wallet.get_free())

    def get_equity(self, asset: Asset):
        equity = Decimal(self.get_available_margin(asset)) + Decimal(self.get_margin_position(asset)) + Decimal(self.get_pnl(asset)) + Decimal(self.get_locked_amount(asset))

        return get_margin_coin_presentation_balance(asset.symbol, equity)

    def get_locked_amount(self, asset: Asset):
        cross_wallet = self.get_asset(asset).get('cross_wallet')
        if not cross_wallet:
            return Decimal('0')

        return get_margin_coin_presentation_balance(asset.symbol, cross_wallet.locked)

    def get_pnl(self, asset: Asset):
        return get_margin_coin_presentation_balance(asset.symbol, self.get_asset(asset).get('pnl'))

    class Meta:
        model = Asset
        fields = (*AssetSerializerMini.Meta.fields, 'equity', 'margin_position', 'available_margin', 'locked_amount', 'pnl')
        ref_name = 'margin assets'


class MarginAssetViewSet(ModelViewSet):
    serializer_class = MarginAssetSerializer
    queryset = Asset.live_objects.filter(Q(pair__margin_enable=True) | Q(trading_pair__margin_enable=True),
                                         symbol__in=[Asset.IRT, Asset.USDT]).distinct()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        account = self.request.user.get_account()
        cross_wallets = Wallet.objects.filter(account=account, market=Wallet.MARGIN, variant__isnull=True)

        positions = MarginPosition.objects.filter(account=account, status=MarginPosition.OPEN).prefetch_related('symbol')

        irt_queryset = positions.filter(base_wallet__asset__symbol=Asset.IRT)
        irt_positions = irt_queryset.annotate(
            position_amount=F('asset_wallet__balance') * F('symbol__last_trade_price') + F('base_wallet__balance'),
            pnl=F('position_amount') - F('equity')
            ).aggregate(s=Sum('position_amount'), p=Sum('pnl'), e=Sum('equity'))

        ctx[Asset.IRT] = {
            'pnl': (irt_positions['p'] or Decimal('0')),
            'equity': irt_positions['e'] or Decimal('0'),
            'cross_wallet': cross_wallets.filter(asset__symbol=Asset.IRT).first()
        }

        usdt_queryset = positions.filter(base_wallet__asset__symbol=Asset.USDT)
        usdt_positions = usdt_queryset.annotate(
            position_amount=F('asset_wallet__balance') * F('symbol__last_trade_price') + F('base_wallet__balance'),
            pnl=F('position_amount') - F('equity')
            ).aggregate(s=Sum('position_amount'), p=Sum('pnl'), e=Sum('equity'))

        ctx[Asset.USDT] = {
            'pnl': (usdt_positions['p'] or Decimal('0')),
            'equity': usdt_positions['e'] or Decimal('0'),
            'cross_wallet': cross_wallets.filter(asset__symbol=Asset.USDT).first()
        }

        return ctx


class MarginBalanceAPIView(APIView):
    """
    loanable balance
    """
    def get(self, request: Request):
        account = request.user.account
        symbol_name = request.query_params.get('symbol')
        symbol = PairSymbol.objects.filter(name=symbol_name, enable=True, margin_enable=True).first()

        if not symbol:
            raise ValidationError(_('{symbol} is not enable').format(symbol=symbol_name))

        side = request.query_params.get('side')
        if side == SELL:
            margin_cross_wallet = symbol.base_asset.get_wallet(account, market=Wallet.MARGIN, variant=None)
            return Response({
                'asset': symbol.base_asset.symbol,
                'balance': get_presentation_amount(margin_cross_wallet.get_free())
            })

        position = MarginPosition.objects.filter(
            account=account, symbol=symbol, status=MarginPosition.OPEN).first()
        if not position or not position.amount:
            return Response({'asset': symbol.asset.symbol, 'balance': get_presentation_amount(Decimal(0))})

        fee_rate = symbol.get_fee_rate(account, is_maker=False)

        return Response({
            'asset': symbol.asset.symbol,
            'balance': get_presentation_amount(position.amount / (Decimal(1) - fee_rate), symbol.step_size)
        })


class MarginTransferBalanceAPIView(APIView):

    def get(self, request: Request):
        transfer_type = request.query_params.get('transfer_type')
        from ledger.models import MarginTransfer
        if transfer_type in MarginTransfer.MARGIN_TO_SPOT:
            base_asset = Asset.get(request.query_params.get('symbol'))
            margin_cross_wallet = base_asset.get_wallet(request.user.account, market=Wallet.MARGIN, variant=None)

            return Response({
                'asset': base_asset.symbol,
                'balance': get_coin_presentation_balance(base_asset.symbol, margin_cross_wallet.get_free())
            })

        elif transfer_type in [MarginTransfer.POSITION_TO_MARGIN, MarginTransfer.MARGIN_TO_POSITION]:
            symbol_name = request.query_params.get('symbol')
            position_id = request.query_params.get('id')
            symbol = PairSymbol.objects.filter(name=symbol_name, enable=True, margin_enable=True).first()

            if not symbol:
                raise ValidationError(_('{symbol} is not enable').format(symbol=symbol_name))

            if not position_id:
                raise ValidationError(_('PositionNullError'))

            position = get_object_or_404(
                MarginPosition,
                account=request.user.account,
                id=position_id,
                symbol=symbol,
                status=MarginPosition.OPEN
            )

            if not position or not position.status in [MarginPosition.CLOSED, MarginPosition.OPEN]:
                return Response({
                    'asset': symbol.base_asset.symbol,
                    'balance': Decimal('0')
                })
            else:
                if transfer_type == MarginTransfer.POSITION_TO_MARGIN:
                    balance = get_margin_coin_presentation_balance(symbol.base_asset.symbol, position.withdrawable_base_asset)
                else:
                    margin_cross_wallet = symbol.base_asset.get_wallet(request.user.account, market=Wallet.MARGIN, variant=None)
                    balance = get_margin_coin_presentation_balance(symbol.base_asset.symbol, margin_cross_wallet.get_free())

                    if position.side == LONG:
                        balance = get_margin_coin_presentation_balance(symbol.base_asset.symbol, min(Decimal(balance), position.debt_amount))

                return Response({
                    'asset': symbol.base_asset.symbol,
                    'balance': balance
                })

        elif transfer_type == MarginTransfer.SPOT_TO_MARGIN:
            base_asset = Asset.get(request.query_params.get('symbol'))
            spot_wallet = base_asset.get_wallet(request.user.account, market=Wallet.SPOT, variant=None)

            return Response({
                            'asset': base_asset.symbol,
                            'balance': get_margin_coin_presentation_balance(base_asset.symbol, spot_wallet.get_free())
                        })
        else:
            return Response({'Error': 'Invalid type'}, status=400)
