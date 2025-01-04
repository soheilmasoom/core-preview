from uuid import uuid4

from rest_framework import serializers

from ledger.models import Wallet, Asset
from ledger.utils.wallet_pipeline import WalletPipeline
from .models import Treasury, PhysicalWithdraw


class TreasurySerializer(serializers.ModelSerializer):
    class Meta:
        model = Treasury
        fields = [
            'id',
            'metal_type',
            'current_balance',
            'sold_amount',
            'bank_reserved',
            'last_updated'
        ]


class PhysicalWithdrawSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhysicalWithdraw
        fields = ['asset', 'amount']

    asset = serializers.SlugRelatedField(
        queryset=Asset.objects.all(),
        slug_field='symbol'
    )

    def validate_amount(self, value):
        if value % 5 != 0:
            raise serializers.ValidationError('درخواست برداشت باید مضربی از پنج باشد.')
        if value <= 0:
            raise serializers.ValidationError('مقدار باید بیشتر از صفر باشد.')
        return value

    def create(self, validated_data):
        from ledger.models import Asset
        account = self.context['request'].user.account
        asset_name = validated_data['asset']

        amount = validated_data['amount']

        asset = Asset.objects.get(symbol=asset_name)

        if asset is None:
            raise serializers.ValidationError('Invalid asset')
        if asset.is_xau_milligrams:
            # physical withdraw is based on gram only
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
