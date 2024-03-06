from decimal import Decimal, InvalidOperation

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView, get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account, LoginActivity
from accounts.permissions import can_trade
from ledger.exceptions import InsufficientBalance, SmallAmountTrade, AbruptDecrease, HedgeError, LargeAmountTrade, \
    SmallDepthError, NoPriceError
from ledger.models import OTCRequest, Asset, OTCTrade, Wallet
from ledger.models.asset import InvalidAmount
from ledger.models.otc_trade import TokenExpired
from ledger.utils.external_price import BUY, SIDE_VERBOSE
from ledger.utils.fields import get_serializer_amount_field
from ledger.utils.otc import get_trading_pair
from ledger.utils.precision import get_symbol_presentation_amount, get_symbol_presentation_price


class OTCInfoView(APIView):
    permission_classes = []

    def get(self, request: Request):
        from_symbol = request.query_params.get('from')
        to_symbol = request.query_params.get('to')

        if from_symbol == to_symbol:
            raise ValidationError('دو ارز دیجیتال باید متفاوت باشند.')

        try:
            from_amount = request.query_params.get('from_amount')
            if from_amount:
                from_amount = Decimal(from_amount)
            else:
                from_amount = None

            to_amount = request.query_params.get('to_amount')
            if to_amount:
                to_amount = Decimal(to_amount)
            else:
                to_amount = None

        except InvalidOperation:
            raise ValidationError({
                'amount': 'مقدار نامعتبر است.'
            })

        from_asset = get_object_or_404(Asset, symbol=from_symbol)
        to_asset = get_object_or_404(Asset, symbol=to_symbol)

        if from_amount and to_amount:
            raise ValidationError({'amount': 'دقیقا یکی از این مقادیر می‌تواند پر باشد.'})

        if not from_amount and not to_amount:
            if from_asset.symbol in (Asset.IRT, Asset.USDT):
                from_amount = Decimal(1)
            else:
                to_amount = Decimal(1)

        try:
            otc = OTCRequest.get_otc_request(
                account=Account.get_for(self.request.user),
                from_asset=from_asset,
                to_asset=to_asset,
                from_amount=from_amount,
                to_amount=to_amount
            )
        except SmallDepthError as exp:
            pair = get_trading_pair(from_asset, to_asset)
            max_amount = get_symbol_presentation_amount(pair.symbol, exp.args[0])
            side_verbose = SIDE_VERBOSE[pair.side]

            if max_amount == 0:
                raise ValidationError(f'در حال حاضر امکان {side_verbose} این ارز دیجیتال وجود ندارد.')
            else:
                raise ValidationError(
                    f'حداکثر مقدار قابل {side_verbose} این ارز دیجیتال {max_amount} {pair.coin} است.'
                )

        except NoPriceError:
            raise ValidationError('در حال حاضر امکان معامله این ارز دیجیتال وجود ندارد.')

        symbol = otc.symbol

        risky = False
        category = symbol.asset.spread_category

        if category and category.name == 'high-risk':
            risky = True

        if otc.side == BUY:
            from_precision, to_precision = Asset.PRECISION, symbol.step_size
        else:
            from_precision, to_precision = symbol.step_size, Asset.PRECISION

        return Response({
            'base_asset': symbol.base_asset.symbol,
            'asset': symbol.asset.symbol,
            'side': otc.side,
            'price': get_symbol_presentation_price(otc.symbol.name, otc.price),
            'to_price': otc.price if otc.side == BUY else 1 / otc.price,
            'risky': risky,
            'from_precision': from_precision,
            'to_precision': to_precision,
        })


class OTCRequestSerializer(serializers.ModelSerializer):
    from_asset = serializers.CharField(source='from_asset.symbol')
    to_asset = serializers.CharField(source='to_asset.symbol')
    from_amount = get_serializer_amount_field(allow_null=True, required=False, write_only=True)
    to_amount = get_serializer_amount_field(allow_null=True, required=False, write_only=True)

    paying_amount = serializers.SerializerMethodField()
    receiving_amount = serializers.SerializerMethodField()
    net_receiving_amount = serializers.SerializerMethodField()

    expire = serializers.SerializerMethodField()
    price = get_serializer_amount_field(read_only=True)
    asset = serializers.CharField(source='symbol.asset.symbol', read_only=True)
    base_asset = serializers.CharField(source='symbol.base_asset.symbol', read_only=True)
    fee = get_serializer_amount_field(source='fee_amount', read_only=True)

    def validate(self, attrs):
        from_symbol = attrs['from_asset']['symbol']
        to_symbol = attrs['to_asset']['symbol']

        if not {Asset.IRT, Asset.USDT} & {from_symbol, to_symbol}:
            raise ValidationError('یکی از دارایی‌ها باید تومان یا تتر باشد.')

        if from_symbol == to_symbol:
            raise ValidationError('هر دو دارایی نمی‌تواند یکی باشد.')

        try:
            from_asset = attrs['from_asset'] = Asset.get(from_symbol)
            to_asset = attrs['to_asset'] = Asset.get(to_symbol)
        except:
            raise ValidationError('دارایی نامعتبر است.')

        if not from_asset.trade_enable or not to_asset.trade_enable:
            raise ValidationError('در حال حاضر امکان معامله این رمزارز وجود ندارد.')

        from_amount = attrs.get('from_amount')
        to_amount = attrs.get('to_amount')

        if not from_amount and not to_amount:
            raise ValidationError('یک مقدار باید وارد شود.')

        if from_amount and to_amount:
            raise ValidationError('یک مقدار باید وارد شود.')

        return attrs

    def create(self, validated_data):
        request = self.context['request']
        account = request.user.get_account()

        if not can_trade(request):
            raise ValidationError('در حال حاضر امکان معامله وجود ندارد.')

        from_asset = validated_data['from_asset']
        to_asset = validated_data['to_asset']

        to_amount = validated_data.get('to_amount')
        from_amount = validated_data.get('from_amount')

        try:
            otc_request = OTCRequest.new_trade(
                account=account,
                from_asset=from_asset,
                to_asset=to_asset,
                from_amount=from_amount,
                to_amount=to_amount,
                market=Wallet.SPOT
            )
            otc_request.login_activity = LoginActivity.from_request(request=request)
            otc_request.save(update_fields=['login_activity'])

            return otc_request
        except InvalidAmount as e:
            raise ValidationError(str(e))
        except SmallAmountTrade:
            raise ValidationError('ارزش معامله، باید حداقل ۱۰,۰۰۰ تومان باشد.')
        except LargeAmountTrade:
            raise ValidationError('ارزش معامله، حداکثر ۲ میلیارد تومان می‌تواند باشد.')
        except InsufficientBalance:
            raise ValidationError({'amount': 'موجودی کافی نیست.'})
        except SmallDepthError as exp:
            pair = get_trading_pair(from_asset, to_asset)
            max_amount = get_symbol_presentation_amount(pair.symbol, exp.args[0])
            side_verbose = SIDE_VERBOSE[pair.side]

            if max_amount == 0:
                raise ValidationError('در حال حاضر امکان {} این رمزارز وجود ندارد.'.format(side_verbose))
            else:
                raise ValidationError(
                    'حداکثر مقدار قابل {} این رمزارز {} {} است.'.format(side_verbose, max_amount, pair.coin)
                )

    def get_expire(self, otc: OTCRequest):
        return otc.get_expire_time()

    def get_paying_amount(self, otc_request: OTCRequest) -> Decimal:
        return otc_request.get_paying_amount()

    def get_receiving_amount(self, otc_request: OTCRequest) -> Decimal:
        return otc_request.get_receiving_amount()

    def get_net_receiving_amount(self, otc_request: OTCRequest) -> Decimal:
        return otc_request.get_net_receiving_amount()

    class Meta:
        model = OTCRequest
        fields = ('from_asset', 'to_asset', 'from_amount', 'to_amount',
                  'token', 'expire', 'price', 'asset', 'base_asset', 'paying_amount', 'receiving_amount',
                  'net_receiving_amount', 'fee')


class OTCTradeRequestView(CreateAPIView):
    serializer_class = OTCRequestSerializer


class OTCTradeSerializer(serializers.ModelSerializer):
    token = serializers.CharField(write_only=True)

    class Meta:
        model = OTCTrade
        fields = ('id', 'token', 'status')
        read_only_fields = ('token', )

    def create(self, validated_data):
        token = validated_data['token']
        request = self.context['request']

        if not can_trade(request):
            raise ValidationError('در حال حاضر امکان معامله وجود ندارد.')

        otc_request = get_object_or_404(OTCRequest, token=token, account=request.user.get_account())

        otc_trade = OTCTrade.objects.filter(otc_request=otc_request).first()
        if otc_trade:
            return otc_trade

        try:
            return OTCTrade.execute_trade(otc_request)
        except TokenExpired:
            raise ValidationError({'token': 'سفارش منقضی شده است. لطفا دوباره اقدام کنید.'})
        except InsufficientBalance:
            raise ValidationError({'amount': 'موجودی کافی نیست.'})
        except InvalidAmount as e:
            raise ValidationError(str(e))
        except AbruptDecrease as e:
            raise ValidationError('مشکلی در ثبت سفارش رخ داد. لطفا دوباره تلاش کنید.')
        except HedgeError as e:
            raise ValidationError('مشکلی در پردازش سفارش رخ داد.')


class OTCTradeView(CreateAPIView):
    serializer_class = OTCTradeSerializer
