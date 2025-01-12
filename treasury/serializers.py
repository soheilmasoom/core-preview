from uuid import uuid4

from rest_framework import serializers

from ledger.models import Asset, Wallet
from ledger.utils.wallet_pipeline import WalletPipeline
from treasury.models import PhysicalWithdraw


class TreasurySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    metal_type = serializers.CharField()
    current_balance = serializers.DecimalField(max_digits=20, decimal_places=8)
    sold_amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    bank_reserved = serializers.DecimalField(max_digits=20, decimal_places=8)
    last_updated = serializers.DateTimeField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return data


class PhysicalWithdrawSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    asset = serializers.SlugRelatedField(
        queryset=Asset.objects.all(),
        slug_field='symbol'
    )
    amount = serializers.DecimalField(max_digits=20, decimal_places=8)
    created_at = serializers.DateTimeField(read_only=True)

    def validate_amount(self, value):
        if value % 5 != 0:
            raise serializers.ValidationError('درخواست برداشت باید مضربی از پنج باشد.')
        if value <= 0:
            raise serializers.ValidationError('مقدار باید بیشتر از صفر باشد.')
        return value

    def create(self, validated_data):
        account = self.context['request'].user.account
        asset_name = validated_data['asset']
        amount = validated_data['amount']

        asset = Asset.objects.get(symbol=asset_name)
        if asset is None:
            raise serializers.ValidationError('Invalid asset')

        if asset.is_xau_milligrams:
            amount = amount * 1000

        wallet = asset.get_wallet(account, market=Wallet.SPOT, variant=None)
        lock_id = uuid4()

        with WalletPipeline() as pipeline:
            wallet.has_balance(amount, raise_exception=True)
            pipeline.new_lock(
                key=lock_id,
                wallet=wallet,
                amount=amount,
                reason=WalletPipeline.WITHDRAW
            )

            withdraw = PhysicalWithdraw.objects.create(
                account=account,
                asset=asset,
                amount=amount,
                lock_id=lock_id,
            )

        return withdraw
