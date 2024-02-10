import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models import VerificationCode, LoginActivity
from accounts.permissions import IsBasicVerified
from financial.models import FiatWithdrawRequest, Gateway
from financial.models.bank_card import BankAccount, BankAccountSerializer
from financial.utils.withdraw_limit import user_reached_fiat_withdraw_limit
from financial.utils.withdraw_verify import auto_verify_fiat_withdraw
from ledger.exceptions import InsufficientBalance
from ledger.models import Asset
from ledger.utils.fields import PENDING, DONE, CANCELED, INIT, PROCESS
from ledger.utils.price import get_last_price, USDT_IRT
from ledger.utils.wallet_pipeline import WalletPipeline
from ledger.utils.withdraw_verify import can_withdraw

logger = logging.getLogger(__name__)

MIN_WITHDRAW = 20_000
MAX_WITHDRAW = 100_000_000


class WithdrawRequestSerializer(serializers.ModelSerializer):
    iban = serializers.CharField(write_only=True)
    code = serializers.CharField(write_only=True)
    totp = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        account = user.get_account()
        amount = validated_data['amount']
        usdt_price = get_last_price(USDT_IRT)

        if not can_withdraw(account, request, value_usdt=usdt_price and amount / usdt_price):
            raise ValidationError('امکان برداشت وجود ندارد.')

        if user.level < user.LEVEL2:
            raise ValidationError('برای برداشت ابتدا احراز هویت نمایید.')

        iban = validated_data['iban']
        code = validated_data['code']
        totp = validated_data.get('totp', None)
        bank_account = get_object_or_404(BankAccount, iban=iban, user=user, verified=True, deleted=False)

        assert account.is_ordinary_user()

        if not bank_account.verified:
            logger.info('FiatRequest rejected due to unverified bank account. user=%s' % user.id)
            raise ValidationError({'iban': 'شماره حساب تایید نشده است.'})

        otp_code = VerificationCode.get_by_code(code, user.phone, VerificationCode.SCOPE_FIAT_WITHDRAW)

        if not otp_code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})
        if not user.is_2fa_valid(totp):
            raise ValidationError({'totp': 'شناسه‌ دوعاملی صحیح نمی‌باشد.'})

        if amount < MIN_WITHDRAW:
            logger.info('FiatRequest rejected due to small amount. user=%s' % user.id)
            raise ValidationError({'iban': 'مقدار وارد شده کمتر از حد مجاز است.'})

        # today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # today_withdraws = FiatWithdrawRequest.objects.filter(
        #     bank_account=bank_account,
        #     created__gte=today,
        # ).exclude(
        #     status=CANCELED
        # ).aggregate(amount=Sum('amount'))['amount'] or 0

        # todo: move to gateway model
        if amount > MAX_WITHDRAW:
            logger.info('FiatRequest rejected due to large amount. user=%s' % user.id)
            raise ValidationError({'amount': 'حداکثر میزان برداشت ۱۰۰ میلیون تومان است.'})

        asset = Asset.get(Asset.IRT)
        wallet = asset.get_wallet(account)

        if not wallet.has_balance(amount):
            raise ValidationError({'amount': 'موجودی کافی نیست.'})

        if user_reached_fiat_withdraw_limit(user, amount):
            logger.info('FiatRequest rejected due to max withdraw limit reached. user=%s' % user.id)
            raise ValidationError({'amount': 'شما به سقف برداشت ریالی خود رسیده اید.'})

        gateway = Gateway.get_active_withdraw(iban=iban)

        if not gateway:
            raise ValidationError('در حال حاضر امکان برداشت وجود ندارد.')

        fee_amount = gateway.get_withdraw_fee(amount=amount)
        withdraw_amount = amount - fee_amount

        try:
            with WalletPipeline() as pipeline:  # type: WalletPipeline
                withdraw_request = FiatWithdrawRequest.objects.create(
                    status=INIT,
                    amount=withdraw_amount,
                    fee_amount=fee_amount,
                    bank_account=bank_account,
                    gateway=gateway,
                    login_activity=LoginActivity.from_request(request=request)
                )

                pipeline.new_lock(
                    key=withdraw_request.group_id,
                    wallet=wallet,
                    amount=amount,
                    reason=WalletPipeline.WITHDRAW
                )

        except InsufficientBalance:
            raise ValidationError({'amount': 'موجودی کافی نیست'})

        if otp_code:
            otp_code.set_code_used()

        if auto_verify_fiat_withdraw(withdraw_request) and not settings.DEBUG_OR_TESTING_OR_STAGING:
            withdraw_request.change_status(PROCESS)

        return withdraw_request

    class Meta:
        model = FiatWithdrawRequest
        fields = ('iban', 'amount', 'code', 'totp')


class WithdrawRequestView(ModelViewSet):
    permission_classes = (IsBasicVerified,)
    serializer_class = WithdrawRequestSerializer

    def get_queryset(self):
        return FiatWithdrawRequest.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if timezone.now() - timedelta(seconds=FiatWithdrawRequest.FREEZE_TIME) > instance.created:
            raise ValidationError('زمان مجاز برای لغو درخواست برداشت گذشته است.')

        if instance.status in (PENDING, DONE):
            raise ValidationError('امکان لغو درخواست برداشت وجود ندارد.')

        instance.change_status(CANCELED)

        return Response({'msg': 'FiatWithdrawRequest Deleted'}, status=status.HTTP_204_NO_CONTENT)


class WithdrawHistorySerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer()
    rial_estimate_receive_time = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = FiatWithdrawRequest
        fields = ('id', 'created', 'status', 'fee_amount', 'amount', 'bank_account', 'ref_id',
                  'rial_estimate_receive_time',)

    def get_rial_estimate_receive_time(self, withdraw_request: FiatWithdrawRequest):
        if withdraw_request.status in (INIT, PROCESS):

            gateway = withdraw_request.gateway

            if gateway.expected_withdraw_datetime and gateway.expected_withdraw_datetime > timezone.now():
                return gateway.expected_withdraw_datetime

        return withdraw_request.receive_datetime

    def get_status(self, withdraw: FiatWithdrawRequest):
        if withdraw.status == INIT:
            return PROCESS
        else:
            return withdraw.status


class WithdrawHistoryView(ListAPIView):
    serializer_class = WithdrawHistorySerializer
    pagination_class = LimitOffsetPagination

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status']

    def get_queryset(self):
        return FiatWithdrawRequest.objects.filter(bank_account__user=self.request.user).order_by('-created')
