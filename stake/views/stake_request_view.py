from django.db.models import Sum, Q
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models import LoginActivity
from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.utils.telegram import send_support_message
from ledger.models import Wallet, Trx
from ledger.utils.precision import get_presentation_amount, floor_precision
from ledger.utils.wallet_pipeline import WalletPipeline
from stake.models import StakeRequest, StakeOption, StakeRevenue
from stake.views.stake_option_view import StakeOptionSerializer


class StakeRequestSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    stake_option_id = serializers.CharField(write_only=True)
    stake_option = StakeOptionSerializer(read_only=True)
    total_revenue = serializers.SerializerMethodField()
    remaining_date = serializers.SerializerMethodField()
    presentation_amount = serializers.SerializerMethodField()

    def get_remaining_date(self, stake_request: StakeRequest):
        if stake_request.remaining_date:
            remaining_seconds = stake_request.remaining_date.total_seconds()
            round_to = 86400  # total seconds in a day
            return str(int((remaining_seconds + round_to / 2) // round_to))

    def get_presentation_amount(self, stake_request: StakeRequest):
        return get_presentation_amount(stake_request.amount)

    def get_total_revenue(self, stake_request: StakeRequest):
        stake_request = stake_request
        return StakeRevenue.objects.filter(stake_request=stake_request).aggregate(Sum('revenue'))['revenue__sum']

    def validate(self, attrs):
        stake_option = StakeOption.objects.get(id=attrs['stake_option_id'])
        amount = floor_precision(attrs['amount'], stake_option.precision)
        user = self.context['request'].user
        asset = stake_option.asset
        wallet = asset.get_wallet(user.get_account())

        if amount <= 0:
            raise ValidationError('مقدار وارد شده باید بزرگتر از صفر باشد.')

        if not stake_option.enable:
            raise ValidationError('امکان استفاده از این گزینه در حال حاضر وجود ندارد.')

        if stake_option.get_free_cap_amount() < amount:
            raise ValidationError('مقدار درخواست شده برای سرمایه گذاری بیشتر از حجم خالی باقی مانده است.')

        if not stake_option.user_min_amount <= amount <= stake_option.user_max_amount:
            raise ValidationError('مقدار وارد شده در بازه مجاز نیست.')

        if stake_option.get_free_amount_per_user(user=user) < amount:
            raise ValidationError('مقدار درخواست شده برای سرمایه گذاری بیشتر از حجم مجاز باقی مانده برای شما است.')

        if not wallet.has_balance(amount=amount):
            raise ValidationError('مقدار وارد شده از موجودی کیف پول شما بیشتر است.')

        return {
            'stake_option': stake_option,
            'amount': amount,
            'account': user.get_account(),
            'wallet': wallet,
            'user': user,
        }

    def create(self, validated_data):
        stake_option = validated_data['stake_option']
        amount = validated_data['amount']
        user = validated_data['user']

        account = user.get_account()
        asset = stake_option.asset

        spot_wallet = asset.get_wallet(account)
        stake_wallet = asset.get_wallet(account=account, market=Wallet.STAKE)

        with WalletPipeline() as pipeline:  # type: WalletPipeline
            stake_object = StakeRequest.objects.create(
                stake_option=stake_option,
                amount=amount,
                account=user.get_account(),
                login_activity=LoginActivity.from_request(self.context['request']),
            )
            pipeline.new_trx(
                group_id=stake_object.group_id,
                sender=spot_wallet,
                receiver=stake_wallet,
                amount=amount,
                scope=Trx.STAKE
            )
        link = url_to_edit_object(stake_object)
        send_support_message(
            message='ثبت درخواست staking برای {} {}'.format(stake_object.stake_option.asset, stake_object.amount,),
            link=link
        )
        return stake_object

    class Meta:
        model = StakeRequest
        fields = ('id', 'created', 'status', 'stake_option', 'amount', 'presentation_amount',
                  'stake_option_id', 'total_revenue', 'remaining_date')


class StakeRequestAPIView(ModelViewSet):
    serializer_class = StakeRequestSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return StakeRequest.objects.none()

        q = Q()

        if self.request.query_params.get('bot', '0') == '1':
            q = Q(stake_option__type=StakeOption.BOT)

        return StakeRequest.objects.filter(
            q,
            account=self.request.user.get_account(),
        ).order_by('-created')

    def destroy(self, request, *args, **kwargs):

        instance = get_object_or_404(StakeRequest, pk=kwargs['pk'], account=self.request.user.get_account())

        if instance.status == StakeRequest.PROCESS:
            instance.change_status(new_status=StakeRequest.CANCEL_COMPLETE)

        elif instance.status in (StakeRequest.PENDING, StakeRequest.DONE):
            instance.change_status(new_status=StakeRequest.CANCEL_PROCESS)

        return Response({'msg': 'stake_request canceled'}, status=status.HTTP_204_NO_CONTENT)
