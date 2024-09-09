import logging
from decimal import Decimal

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import WidgetJWTAuthentication
from accounts.models import SystemConfig
from financial.views.payment_view import PaymentRequestSerializer
from ledger.exceptions import SmallDepthError
from ledger.models import OTCRequest, Wallet
from ledger.models.asset import CoinField, Asset
from ledger.models.fast_buy_token import FastBuyToken
from ledger.utils.external_price import SELL, BUY
from ledger.utils.precision import get_symbol_presentation_amount
from ledger.utils.price import get_price
from financial.models import Gateway

logger = logging.getLogger(__name__)

class FastBuyWidgetSerializer(serializers.ModelSerializer):
    coin = CoinField(source='asset')
    callback = serializers.SerializerMethodField(read_only=True)

    def get_callback(self, fast_buy_token: FastBuyToken):
        payment_request = fast_buy_token.payment_request
        return payment_request.get_gateway().get_initial_redirect_url(payment_request)

    def validate(self, attrs):
        min_fast_buy_irt = SystemConfig.get_system_config().min_fast_buy_irt
        if attrs['amount'] < min_fast_buy_irt:
            raise ValidationError(f'حداقل مقدار سفارش {min_fast_buy_irt} هزار تومان است.')
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        user = request.user

        payment_request_serializer = PaymentRequestSerializer()
        payment_request_serializer.context['request'] = request

        asset = validated_data['asset']
        if asset.otc_status not in (BUY, Asset.ACTIVE):
            raise ValidationError('امکان خرید این رمزارز وجود ندارد.')

        try:
            OTCRequest.get_otc_request(
                account=user.get_account(),
                from_asset=Asset.get('IRT'),
                to_asset=asset,
                from_amount=Decimal(validated_data['amount']),
                market=Wallet.SPOT,
                order_type=OTCRequest.MARKET
            )
        except SmallDepthError as exp:
            max_amount = get_symbol_presentation_amount(f'{asset}IRT', exp.args[0])
            if max_amount == 0:
                raise ValidationError('در حال حاضر امکان خرید این رمزارز وجود ندارد.')
            else:
                raise ValidationError(
                    'حداکثر مقدار قابل خرید این رمزارز {} {} است.'.format(max_amount, asset.symbol)
                )

        validated_data['is_bank_card_required'] = False
        validated_data['payment_request'] = payment_request_serializer.create(validated_data)
        validated_data.pop('is_bank_card_required')
        validated_data['price'] = get_price(
            asset.symbol + Asset.USDT,
            side=SELL
        )

        return super().create(validated_data)

    class Meta:
        model = FastBuyToken
        fields = ('coin', 'amount', 'callback')
        read_only_fields = ('callback', )

class FastBuyWidgetView(CreateAPIView):
    authentication_classes = (WidgetJWTAuthentication,)
    serializer_class = FastBuyWidgetSerializer
    queryset = FastBuyToken.objects.all()


class WidgetConfigView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        return Response(
            {
                'is_fast_buy_enable': Gateway.get_active_deposit(widget_deposit_enable=True).exists(),
                'min_irt_value': SystemConfig.get_system_config().min_fast_buy_irt
            }
        )