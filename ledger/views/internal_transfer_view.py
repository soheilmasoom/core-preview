from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from django.db.models import Q
from django.db import transaction
from ledger.models import InternalTransfer, Asset, Wallet
from accounts.models import User

class InternalTransferSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(source='sender_wallet.account.user.username', read_only=True)
    receiver = serializers.CharField(write_only=True)
    asset = serializers.CharField(write_only=True)

    class Meta:
        model = InternalTransfer
        fields = ['id', 'sender', 'receiver', 'asset', 'amount', 'status', 'created', 'description']
        read_only_fields = ['id', 'sender', 'status', 'created']

    def validate(self, attrs):
        user = self.context['request'].user
        receiver_username = attrs.pop('receiver')
        asset_symbol = attrs.pop('asset')

        try:
            receiver = User.objects.get(username=receiver_username)
        except User.DoesNotExist:
            raise serializers.ValidationError({'receiver': 'کاربر پیدا نشد.'})

        try:
            asset = Asset.objects.get(symbol=asset_symbol)
        except Asset.DoesNotExist:
            raise serializers.ValidationError({'asset': 'رمز ارز یافت نشد.'})

        sender_wallet = Wallet.objects.get(account=user.get_account(), asset=asset)
        receiver_wallet = Wallet.objects.get(account=receiver.get_account(), asset=asset)

        if not sender_wallet.has_balance(attrs['amount']):
            raise serializers.ValidationError({'amount': 'موجودی کافی نیست.'})

        attrs['sender_wallet'] = sender_wallet
        attrs['receiver_wallet'] = receiver_wallet

        return attrs

    def create(self, validated_data):
        return InternalTransfer.new_internal_transfer(
            sender_wallet=validated_data['sender_wallet'],
            receiver_wallet=validated_data['receiver_wallet'],
            amount=validated_data['amount'],
            description=validated_data.get('description', '')
        )


class InternalTransferViewSet(viewsets.ModelViewSet):
    serializer_class = InternalTransferSerializer
    queryset = InternalTransfer.objects.all()

    def get_queryset(self):
        user = self.request.user
        account = user.get_account()
        return InternalTransfer.objects.filter(
            Q(sender_wallet__account=account) |
            Q(receiver_wallet__account=account)
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            internal_transfer = serializer.save()
            internal_transfer.accept()
        return Response(serializer.data, status=status.HTTP_201_CREATED)