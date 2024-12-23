from rest_framework import serializers
from .models import Treasury


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
