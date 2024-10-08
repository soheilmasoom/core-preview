from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from django.db.models import Q
from django.db import transaction
from accounts.models.login_activity import LoginActivity
from accounts.models.phone_verification import VerificationCode
from accounts.models.user import LevelGrants
from financial.utils.withdraw_limit import get_crypto_withdraw_irt_value
from ledger.models import InternalTransfer, Asset, Wallet
from accounts.models import User
from accounts.utils.validation import persian_timedelta
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from accounts.validators import mobile_number_validator
from ledger.utils.precision import get_precision, get_presentation_amount, humanize_number
from ledger.utils.price import get_last_price
from ledger.utils.withdraw_verify import can_withdraw
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from accounts.authentication import CustomJWTAuthentication, WithdrawTokenAuthentication
from rest_framework.authentication import SessionAuthentication


class InternalTransferSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(source='sender_account.user.phone', read_only=True)
    receiver_phone = serializers.CharField(write_only=True, required=True, validators=[mobile_number_validator], trim_whitespace=True)
    asset = serializers.CharField(required=True)
    code = serializers.CharField(write_only=True, required=False)
    totp = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)


    class Meta:
        model = InternalTransfer
        fields = ['id', 'totp', 'code','sender', 'receiver_phone', 'asset', 'amount', 'status', 'created', 'description']
        read_only_fields = ['id', 'sender', 'status', 'created']

    def validate(self, attrs):
        user = self.context['request'].user
        receiver_phone = attrs['receiver_phone']
        asset_symbol = attrs['asset']

        if user.is_suspended:
            td = persian_timedelta(user.suspended_until - timezone.now())

            raise ValidationError(
                f'به دلیل افزایش امنیت حساب‌ کاربری شما، امکان ‌برداشت تا {td} دیگر وجود ندارد.'
            )

        try:
            receiver = User.objects.get(phone=receiver_phone)
        except User.DoesNotExist:
            raise serializers.ValidationError({'receiver': 'کاربر پیدا نشد.'})

        try:
            asset = Asset.objects.get(symbol=asset_symbol)
        except Asset.DoesNotExist:
            raise serializers.ValidationError({'asset': 'رمز ارز یافت نشد.'})

        amount = attrs['amount']
        totp = attrs.get('totp', None)

        if get_precision(amount) > Asset.PRECISION:
            raise serializers.ValidationError('مقدار وارد شده اشتباه است.')

        if asset.symbol == Asset.IRT:
            raise ValidationError('نشانه دارایی اشتباه است.')

        sms_verification_code = None

        code = attrs.get('code')
        if not code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})

        sms_verification_code = VerificationCode.get_by_code(code, user.phone, VerificationCode.SCOPE_CRYPTO_WITHDRAW, user=user)

        if not sms_verification_code:
            raise ValidationError({'code': 'کد پیامکی  نامعتبر است.'})

        if not user.is_2fa_valid(totp):
            raise ValidationError({'totp': 'شناسه‌ دوعاملی صحیح نمی‌باشد.'})

        sender_wallet = asset.get_wallet(user.get_account())
        sender_account = user.get_account()
        receiver_account = receiver.get_account()

        if not sender_wallet.has_balance(attrs['amount']):
            raise serializers.ValidationError({'amount': 'موجودی کافی نیست.'})

        attrs['sender_account'] = sender_account
        attrs['receiver_account'] = receiver_account

        usdt_price = get_last_price(asset.symbol + Asset.USDT)
        value_usdt = usdt_price and amount * usdt_price

        if not can_withdraw(user.get_account(), self.context['request'], value_usdt=value_usdt) or not user.can_withdraw_crypto:
            raise ValidationError('امکان برداشت وجود ندارد.')

        irt_price = get_last_price(asset.symbol + Asset.IRT)

        if asset.enable or irt_price:
            irt_value = irt_price * amount
            ceil = LevelGrants.get_max_daily_crypto_withdraw(user)
            today_withdraw_value = get_crypto_withdraw_irt_value(user)
            if irt_value >= ceil:
                raise ValidationError({'amount': 'مبلغ برداشتی بیش از میزان مجاز سطح کاربری شماست.'})

            if today_withdraw_value + irt_value >= ceil:
                raise ValidationError({'amount': 'شما به سقف برداشت روزانه ارز دیجیتال خود رسیده اید.'})

        if sms_verification_code:
            sms_verification_code.set_code_used()

        return attrs

    def create(self, validated_data):
        internal_tranfer = InternalTransfer.new_internal_transfer(
            sender_account=validated_data['sender_account'],
            receiver_account=validated_data['receiver_account'],
            amount=validated_data['amount'],
            asset=Asset.objects.get(symbol=validated_data['asset']),
            description=validated_data.get('description', '')
        )
        internal_tranfer.login_activity = LoginActivity.from_request(request=self.context['request'])
        internal_tranfer.save(update_fields=['login_activity'])
        return internal_tranfer


class InternalTransferViewSet(viewsets.ModelViewSet):
    authentication_classes = (SessionAuthentication, WithdrawTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    serializer_class = InternalTransferSerializer
    queryset = InternalTransfer.objects.all()

    def get_queryset(self):
        user = self.request.user
        account = user.get_account()
        return InternalTransfer.objects.filter(
            Q(sender_account=account) |
            Q(receiver_account=account)
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            internal_transfer = serializer.save()
            internal_transfer.accept()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        internal_transfer = self.get_object()
        if internal_transfer.status in InternalTransfer.COMPLETE_STATUSES:
            return Response({"detail": "لغو مجاز نمی‌باشد."}, status=status.HTTP_400_BAD_REQUEST)

        internal_transfer.reject()

        return Response(status=status.HTTP_204_NO_CONTENT)
