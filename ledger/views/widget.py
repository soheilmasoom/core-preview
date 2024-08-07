import logging

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, CreateAPIView

from ledger.models.fast_buy_widget import FastBuyWidget
from ledger.utils.fields import PENDING, DONE, PROCESS, CANCELED
from ledger.models.asset import CoinField

logger = logging.getLogger(__name__)


class FastBuyWidgetSerializer(serializers.ModelSerializer):
    coin = CoinField(source='asset')
    callback = serializers.SerializerMethodField(read_only=True)

    def get_callback(self, fast_buy_token: FastBuyToken):
        payment_request = fast_buy_token.payment_request
        return payment_request.get_gateway().get_initial_redirect_url(payment_request)

    def validate(self, attrs):
        if attrs['amount'] < FastBuyToken.MIN_ADMISSIBLE_VALUE:
            raise ValidationError('حداقل مقدار سفارش 300 هزار تومان است.')
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        user = request.user

        payment_request_serializer = PaymentRequestSerializer()
        payment_request_serializer.context['request'] = request
        # card_pan = BankCard.objects.get(id=validated_data['payment_request']['bank_card_id']).card_pan

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
        model = FastBuyWidget
        fields = ('coin', 'amount', 'callback')


class FastBuyWidgetView(CreateAPIView):
    serializer_class = FastBuyWidgetSerializer
    queryset = FastBuyWidget.objects.all()
