from decimal import Decimal

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView

from accounts.models.system_config import SystemConfig
from financial.models import BankCard
from financial.views.payment_view import PaymentRequestSerializer
from ledger.exceptions import SmallDepthError
from ledger.models import OTCRequest, Wallet
from ledger.models.asset import CoinField, Asset
from ledger.models.fast_buy_token import FastBuyToken
from ledger.utils.external_price import SELL, BUY
from ledger.utils.precision import get_symbol_presentation_amount, humanize_number
from ledger.utils.price import get_price


class FastBuyTokenSerializer(serializers.ModelSerializer):
    coin = CoinField(source='asset')
    bank_card_id = serializers.IntegerField(source='payment_request.bank_card_id')
    callback = serializers.SerializerMethodField(read_only=True)

    def get_callback(self, fast_buy_token: FastBuyToken):
        payment_request = fast_buy_token.payment_request
        return payment_request.get_gateway().get_initial_redirect_url(payment_request)

    def validate(self, attrs):
        min_fast_buy_irt = SystemConfig.get_system_config().min_fast_buy_irt
        max_fast_buy_irt = SystemConfig.get_system_config().max_fast_buy_irt

        if attrs['amount'] < min_fast_buy_irt:
            raise ValidationError(f'حداقل مقدار سفارش {humanize_number(min_fast_buy_irt)} تومان است.')

        if attrs['amount'] > max_fast_buy_irt:
            raise ValidationError(f'حداکثر مقدار سفارش {humanize_number(max_fast_buy_irt)} تومان است.')

        return attrs

    def create(self, validated_data):
        request = self.context['request']
        user = request.user

        payment_request_serializer = PaymentRequestSerializer()
        payment_request_serializer.context['request'] = request
        card_pan = BankCard.objects.get(id=validated_data['payment_request']['bank_card_id']).card_pan

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

        validated_data['card_pan'] = card_pan
        validated_data['payment_request'] = payment_request_serializer.create(validated_data)
        validated_data.pop('card_pan')
        validated_data['price'] = get_price(
            asset.symbol + Asset.USDT,
            side=SELL
        )

        return super().create(validated_data)

    class Meta:
        model = FastBuyToken
        fields = ('coin', 'amount', 'bank_card_id', 'callback')


class FastBuyTokenAPI(CreateAPIView):
    serializer_class = FastBuyTokenSerializer
    queryset = FastBuyToken.objects.all()
