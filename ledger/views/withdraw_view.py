import re

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, CreateAPIView, ListAPIView
from rest_framework.viewsets import ModelViewSet

from accounts.authentication import CustomJWTAuthentication, WithdrawTokenAuthentication
from accounts.models import VerificationCode, LoginActivity, User, SmsNotification, LevelGrants
from accounts.models.user_feature_perm import UserFeaturePerm
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from accounts.utils.validation import persian_timedelta
from financial.utils.withdraw_limit import get_crypto_withdraw_irt_value
from ledger.exceptions import InsufficientBalance
from ledger.models import Asset, Transfer, NetworkAsset, AddressBook, DepositAddress
from ledger.models import WithdrawFeedback, FeedbackCategory
from ledger.models.asset import CoinField
from ledger.models.network import NetworkField
from ledger.utils.precision import get_precision, get_presentation_amount, humanize_number
from ledger.utils.price import get_last_price
from ledger.utils.withdraw_verify import can_withdraw
from ledger.views.address_book_view import AddressBookCreateSerializer


class WithdrawSerializer(serializers.ModelSerializer):
    address_book_id = serializers.CharField(write_only=True, required=False, default=None)
    coin = CoinField(source='asset', required=True)
    network = NetworkField(required=False)
    code = serializers.CharField(write_only=True, required=False)
    address = serializers.CharField(source='out_address', required=False)
    memo = serializers.CharField(required=False, allow_blank=True)
    address_book = serializers.SerializerMethodField()
    totp = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        request = self.context['request']
        user = request.user

        if user.is_suspended:
            td = persian_timedelta(user.suspended_until - timezone.now())

            raise ValidationError(
                f'به دلیل افزایش امنیت حساب‌ کاربری شما، امکان ‌برداشت تا {td} دیگر وجود ندارد.'
            )

        account = user.get_account()
        from_panel = self.context.get('from_panel')
        asset = attrs.get('asset')
        network = attrs.get('network')
        address = attrs.get('out_address')
        address_book = None
        totp = attrs.get('totp', None)
        whitelist = False
        memo = attrs.get('memo') or ''

        if attrs['address_book_id'] and from_panel:
            address_book = get_object_or_404(AddressBook, id=attrs['address_book_id'], account=account)
            network = address_book.network

            if address_book.asset:
                if asset != address_book.asset:
                    raise ValidationError('دفترچه آدرس برای این برداشت معتبر نیست.')

            address = address_book.address
            whitelist = address_book.whitelist
            memo = address_book.memo

        else:
            if not asset:
                raise ValidationError('ارز دیجیتالی انتخاب نشده است.')
            if not network:
                raise ValidationError('شبکه‌ای انتخاب نشده است.')
            if not address:
                raise ValidationError('آدرس وارد نشده است.')

            if from_panel and 'code' not in attrs:
                raise ValidationError('کد وارد نشده است.')

        amount = attrs['amount']
        usdt_price = get_last_price(asset.symbol + Asset.USDT)
        value_usdt = usdt_price and amount * usdt_price

        if not can_withdraw(user.get_account(), request, value_usdt=value_usdt) or not user.can_withdraw_crypto:
            raise ValidationError('امکان برداشت وجود ندارد.')

        if not re.match(network.address_regex, address):
            raise ValidationError('آدرس به فرمت درستی وارد نشده است.')

        if asset.symbol == Asset.IRT:
            raise ValidationError('نشانه دارایی اشتباه است.')

        sms_verification_code = None

        if not whitelist:
            ignore_sms_otp = user.is_2fa_active() and \
                             address_book and \
                             user.has_feature_perm(UserFeaturePerm.NO_SMS_FOR_CRYPTO_WITHDRAW)

            if from_panel:
                if not ignore_sms_otp:
                    code = attrs.get('code')
                    if not code:
                        raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})

                    sms_verification_code = VerificationCode.get_by_code(code, user.phone, VerificationCode.SCOPE_CRYPTO_WITHDRAW, user=user)

                    if not sms_verification_code:
                        raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})

                if not user.is_2fa_valid(totp):
                    raise ValidationError({'totp': 'شناسه‌ دوعاملی صحیح نمی‌باشد.'})

        network_asset = get_object_or_404(NetworkAsset, asset=asset, network=network)

        if not network_asset.can_withdraw_enabled():
            raise ValidationError(
                'در حال حاضر امکان برداشت {} روی شبکه {} وجود ندارد.'.format(asset.symbol, network.symbol))

        if get_precision(amount) > network_asset.withdraw_precision:
            raise ValidationError('مقدار وارد شده اشتباه است.')

        if amount < network_asset.withdraw_min:
            raise ValidationError('مقدار وارد شده کوچک است.')

        if amount > network_asset.withdraw_max:
            raise ValidationError('مقدار وارد شده بزرگ است.')

        if DepositAddress.objects.filter(address=address, address_key__deleted=True):
            raise ValidationError('آدرس برداشت نامعتبر است.')

        my_deposit_addresses = DepositAddress.objects.filter(address=address, address_key__account=account)

        if network.withdraw_allow_memo:
            if not memo:
                my_deposit_addresses = DepositAddress.objects.none()
            else:
                my_deposit_addresses = my_deposit_addresses.filter(address_key__memo=memo)
        else:
            memo = ''

        if my_deposit_addresses:
            raise ValidationError('آدرس برداشت متعلق به خودتان است. لطفا آدرس دیگری را وارد نمایید.')

        wallet = asset.get_wallet(account)

        if wallet.market != wallet.SPOT:
            raise ValidationError('کیف پول نادرستی انتخاب شده است.')

        if not wallet.has_balance(amount):
            raise ValidationError('موجودی کافی نیست.')

        # if asset.enable and not check_withdraw_laundering(wallet=wallet, amount=amount):
        #     raise ValidationError(
        #         'در این سطح کاربری نمی‌توانید ریال واریزی را به صورت رمزارز برداشت کنید. لطفا احراز هویت سطح ۳ را انجام دهید.')

        if asset.enable and user.level < User.LEVEL2:
            raise ValidationError('برای برداشت ارز دیجیتال لازم است به سطح 2 احراز هویت کنید.')

        irt_price = get_last_price(asset.symbol + Asset.IRT)

        if asset.enable or irt_price:
            irt_value = irt_price * amount
            ceil = LevelGrants.get_max_daily_crypto_withdraw(user)
            today_withdraw_value = get_crypto_withdraw_irt_value(user)

            if irt_value > ceil:
                raise ValidationError({'amount': 'مبلغ برداشتی بیش از میزان مجاز سطح کاربری شماست.'})

            if today_withdraw_value + irt_value > ceil:
                raise ValidationError({'amount': 'شما به سقف برداشت روزانه ارز دیجیتال خود رسیده اید.'})

        if sms_verification_code:
            sms_verification_code.set_code_used()

        return {
            'network': network,
            'asset': asset,
            'wallet': wallet,
            'amount': amount,
            'out_address': address,
            'account': account,
            'memo': memo,
            'address_book': address_book,
            'whitelist': whitelist
        }

    def create(self, validated_data):
        whitelist = validated_data['whitelist']
        amount = validated_data['amount']
        wallet = validated_data['wallet']

        sms_content = ''

        if whitelist:
            sms_content = render_to_string('accounts/notif/sms/whitelist_crypto_withdraw_success.txt', context={
                'brand': settings.BRAND,
                'amount': humanize_number(amount),
                'coin': wallet.asset.name_fa
            })

        try:
            with transaction.atomic():

                transfer = Transfer.new_withdraw(
                    wallet=wallet,
                    network=validated_data['network'],
                    amount=amount,
                    address=validated_data['out_address'],
                    memo=validated_data['memo'],
                    whitelist=whitelist,
                )

                transfer.login_activity = LoginActivity.from_request(request=self.context['request'])
                transfer.address_book = validated_data['address_book']
                transfer.save(update_fields=['address_book', 'login_activity'])

                if whitelist:
                    SmsNotification.objects.create(
                        recipient=self.context['request'].user,
                        content=sms_content
                    )

                return transfer
        except InsufficientBalance:
            raise ValidationError('موجودی کافی نیست.')

    def get_address_book(self, transfer: Transfer):
        if transfer.address_book:
            return AddressBookCreateSerializer(transfer.address_book).data

    def to_representation(self, order: Transfer):
        data = super(WithdrawSerializer, self).to_representation(order)
        data['amount'] = get_presentation_amount(data['amount'])
        return data

    class Meta:
        model = Transfer
        fields = ('id', 'amount', 'address', 'coin', 'network', 'code', 'address_book_id', 'address_book', 'memo',
                  'totp')
        ref_name = 'Withdraw Serializer'


class WithdrawView(CreateAPIView):
    authentication_classes = (SessionAuthentication, WithdrawTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]
    serializer_class = WithdrawSerializer
    queryset = Transfer.objects.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # ctx['from_panel'] = not isinstance(self.request.successful_authenticator, WithdrawTokenAuthentication)
        ctx['from_panel'] = True
        return ctx


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackCategory
        fields = ('category', 'id',)
        extra_kwargs = {
            'category': {'read_only': True},
            'id': {'read_only': True}
        }


class FeedbackCategories(ListAPIView):
    queryset = FeedbackCategory.objects.all()
    serializer_class = CategorySerializer


class FeedbackSerializer(serializers.ModelSerializer):

    def validate(self, attrs):
        attrs['user'] = self.context['request'].user
        return attrs

    class Meta:
        model = WithdrawFeedback
        fields = ('id', 'category', 'description',)
        extra_kwargs = {
            'category': {'required': True, 'write_only': True},
            'description': {'required': False, 'write_only': True},
        }


class WithdrawFeedbackViewSet(ModelViewSet):
    serializer_class = FeedbackSerializer

    def get_queryset(self):
        user = self.request.user
        return WithdrawFeedback.objects.filter(user=user)
