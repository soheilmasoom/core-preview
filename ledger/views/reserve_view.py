from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account
from accounts.authentication import CustomTokenAuthentication
from accounts.views.jwt_views import user_has_delegate_permission
from ledger.exceptions import InsufficientBalance
from ledger.models import Asset, Wallet
from ledger.models.wallet import ReserveWallet
from ledger.utils.fields import get_serializer_amount_field


class ReserveWalletSerializer(serializers.Serializer):
    account_id = serializers.IntegerField()
    amount = get_serializer_amount_field()
    asset = serializers.CharField()
    request_id = serializers.CharField()
    market = serializers.CharField(default=Wallet.SPOT)

    def create(self, validated_data):
        account = Account.objects.get(id=validated_data['account_id'])
        src_wallet = Asset.get(validated_data['asset']).get_wallet(account, validated_data['market'])
        try:
            return src_wallet.reserve_funds(Decimal(validated_data['amount']), validated_data['request_id'])
        except InsufficientBalance:
            raise ValidationError(_('Insufficient Balance'))

    def update(self, instance, validated_data):
        pass


class RefundWalletSerializer(serializers.Serializer):
    account_id = serializers.IntegerField()
    variant = serializers.CharField()

    def create(self, validated_data):
        account = Account.objects.get(id=validated_data['account_id'])
        variant = validated_data['variant']
        reserve_wallet = ReserveWallet.objects.get(group_id=variant)
        if reserve_wallet.receiver.account != account:
            raise ValidationError(_('Account and Variant do not match together.'))
        
        if reserve_wallet.refund_completed:
            return True

        try:
            from market.models import Order
            with transaction.atomic():
                Order.cancel_orders(Order.open_objects.filter(account=account, wallet__variant=variant))
                return reserve_wallet.refund()
        except InsufficientBalance:
            raise ValidationError(_('Insufficient Balance'))
        except Exception as exp:
            raise ValidationError(f'Refund failed with exception: {exp}')

    def update(self, instance, validated_data):
        pass


class ReserveWalletCreateAPIView(APIView):
    authentication_classes = (CustomTokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request: Request):
        if not user_has_delegate_permission(request.user):
            raise PermissionDenied({'message': _('You do not have permission to perform this action.'), })

        serializer = ReserveWalletSerializer(data={**request.data})
        serializer.is_valid(raise_exception=True)
        return Response({
            'variant': serializer.create(serializer.data),
        })


class ReserveWalletRefundAPIView(APIView):
    authentication_classes = (CustomTokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request: Request):
        if not user_has_delegate_permission(request.user):
            raise PermissionDenied({'message': _('You do not have permission to perform this action.'), })

        serializer = RefundWalletSerializer(data={**request.data})
        serializer.is_valid(raise_exception=True)
        if serializer.create(serializer.data):
            return Response({
                'success': True,
            })
        raise ValidationError(_('Could not refund reserve wallet.'))
