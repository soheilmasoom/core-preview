from rest_framework import serializers
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.viewsets import ModelViewSet

from ledger.models import Prize
from ledger.models.asset import AssetSerializerMini
from ledger.utils.wallet_pipeline import WalletPipeline


class PrizeSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    voucher = serializers.SerializerMethodField()

    def update(self, prize: Prize, validated_data):
        redeemed = validated_data.get('redeemed')

        # Only trigger the wallet pipeline if redeemed is being set to True
        # and the prize wasn't already redeemed
        if redeemed is True and not prize.redeemed:
            with WalletPipeline() as pipeline:
                prize.build_trx(pipeline)
            # build_trx already sets redeemed=True and saves it
            # so we need to refresh the instance
            prize.refresh_from_db()

        # Update other fields if present (excluding 'redeemed' since build_trx handles it)
        update_fields = []
        for attr, value in validated_data.items():
            if attr != 'redeemed' or redeemed is not True:
                # Only set redeemed manually if it's being set to False
                # or if we didn't call build_trx
                setattr(prize, attr, value)
                update_fields.append(attr)

        if update_fields:
            prize.save(update_fields=update_fields)

        return prize

    class Meta:
        model = Prize
        fields = ('id', 'amount', 'asset', 'redeemed', 'reason', 'created', 'voucher', 'voucher_expiration')
        read_only_fields = ('id', 'amount', 'scope', 'coin', 'created')

    def get_reason(self, prize: Prize):
        return ''

    def get_voucher(self, prize: Prize):
        return prize.voucher_expiration is not None

    def get_asset(self, prize: Prize):
        from gamify.models import Achievement

        achievement = prize.achievement

        if achievement.type == Achievement.NORMAL or prize.redeemed:
            return AssetSerializerMini(prize.asset).data

    def get_amount(self, prize: Prize):
        from gamify.models import Achievement

        achievement = prize.achievement

        if achievement.type == Achievement.NORMAL or prize.redeemed:
            return prize.amount


class PrizeView(ModelViewSet):
    serializer_class = PrizeSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        return Prize.objects.filter(account=self.request.user.get_account(), amount__gt=0)
