import logging
from decimal import Decimal

from django.db.models import Q, DateField, Case, When, F, Sum
from django.db.models.functions import Cast
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from accounts.models import Referral, Account, User
from ledger.utils.precision import floor_precision
from market.models import ReferralTrx
from market.models.pair_symbol import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE

logger = logging.getLogger(__name__)


class ReferralSerializer(serializers.ModelSerializer):
    revenue = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    def get_revenue(self, referral: Referral):
        revenue = ReferralTrx.objects.filter(referral=referral).aggregate(total=Sum('referrer_amount'))
        return int(revenue['total'] or 0)

    def get_members(self, referral: Referral):
        return Account.objects.filter(referred_by=referral).count()

    def to_internal_value(self, data):
        try:
            owner_share_percent = int(data['owner_share_percent'])
        except ValueError:
            raise ValidationError({'owner_share_percent': _('A valid integer is required.')})
        return super(ReferralSerializer, self).to_internal_value(
            {'owner_share_percent': owner_share_percent, 'owner': self.context['account'].id}
        )

    def create(self, validated_data):
        user = self.context['request'].user

        if user.level < User.LEVEL2:
            raise ValidationError('برای ساخت کد ریفرال، باید احراز هویت سطح ۲ داشته باشید.')

        return super(ReferralSerializer, self).create(validated_data)

    @staticmethod
    def validate_owner_share_percent(value):
        if value < 0:
            raise ValidationError(_('Invalid share percent'))

        if value > Referral.REFERRAL_MAX_RETURN_PERCENT:
            raise ValidationError(_('Input value is greater than {max_percent}').format(max_percent=Referral.REFERRAL_MAX_RETURN_PERCENT))
        return value

    class Meta:
        model = Referral
        fields = ('id', 'owner', 'created', 'code', 'owner_share_percent', 'revenue', 'members')
        read_only_fields = ('id', 'created', 'code')
        extra_kwargs = {
            'owner': {'write_only': True},
        }


class ReferralTrxSerializer(serializers.Serializer):
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=0)

    def update(self, instance, validated_data):
        pass

    def create(self, validated_data):
        pass


class ReferralViewSet(
        mixins.CreateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet):

    serializer_class = ReferralSerializer

    def get_queryset(self):
        return Referral.objects.filter(owner=self.request.user.get_account())

    def get_serializer_context(self):
        return {
            **super(ReferralViewSet, self).get_serializer_context(),
            'account': self.request.user.get_account()
        }


class ReferralOverviewAPIView(APIView):

    def get(self, request):

        account = request.user.get_account()

        members = Account.objects.filter(referred_by__owner=account).count()
        referred_revenue = ReferralTrx.objects.filter(
            trader=account
        ).aggregate(total=Sum('trader_amount'))['total'] or 0

        referral_revenue = ReferralTrx.objects.filter(
            referral__owner=account
        ).aggregate(total=Sum('referrer_amount'))['total'] or 0

        return Response({
            'members': members,
            'referred_revenue': int(referred_revenue),
            'referral_revenue': int(referral_revenue),
            'total_revenue': int(referred_revenue + referral_revenue)
        })


class ReferralReportAPIView(ListAPIView):
    serializer_class = ReferralTrxSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['referral']

    def get_queryset(self):
        account = self.request.user.get_account()

        return ReferralTrx.objects.filter(
            Q(referral__owner=account) | Q(trader=account)
        ).annotate(
            date=Cast('created', DateField()),
            received_amount=Case(
                When(trader=account, then=F('trader_amount')),
                When(referral__owner=account, then=F('referrer_amount'))
            )
        ).values('date').annotate(amount=Sum('received_amount'))


class TradingFeeView(APIView):

    def get(self, request):
        account = request.user.get_account()
        voucher = account.get_voucher_wallet()

        old_taker_fee = DEFAULT_TAKER_FEE
        old_maker_fee = DEFAULT_MAKER_FEE

        if voucher:
            taker_fee = 0
            expiration = voucher.expiration
            voucher_amount = voucher.balance
        else:
            taker_fee = DEFAULT_TAKER_FEE
            expiration = None
            voucher_amount = None

        maker_fee = Decimal('0')

        referral_code = account.referred_by

        if referral_code:
            referral_percent = Referral.REFERRAL_MAX_RETURN_PERCENT - referral_code.owner_share_percent
            taker_fee = taker_fee * (Decimal('1') - referral_percent / Decimal('100'))

        return Response({
            'old_taker_fee': str(old_taker_fee),
            'old_maker_fee': str(old_maker_fee),
            'taker_fee': str(taker_fee),
            'maker_fee': str(maker_fee),
            'voucher_expiration': expiration,
            'voucher_amount': voucher_amount and floor_precision(voucher_amount, 2),
        })
