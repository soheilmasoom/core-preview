import logging

from django.contrib.auth.mixins import UserPassesTestMixin
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, CreateAPIView

from accounts.authentication import CustomTokenAuthentication
from ledger.models import ManualWithdraw
from ledger.utils.fields import PENDING, DONE, PROCESS, CANCELED

logger = logging.getLogger(__name__)


class ManualWithdrawSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField(write_only=True, source='id')
    status = serializers.CharField(max_length=12, write_only=True)
    trx_hash = serializers.CharField(max_length=128, write_only=True, allow_blank=True, allow_null=True, required=False)

    class Meta:
        model = ManualWithdraw
        fields = ['status', 'requester_id', 'trx_hash', ]
        ref_name = 'Manual Withdraw Update Serializer'

    def create(self, validated_data):
        requester_id = validated_data.get('id')
        status = validated_data.get('status')
        manual_withdraw = get_object_or_404(ManualWithdraw, id=requester_id)

        TERMINATE = 'terminate'
        if status not in [PROCESS, PENDING, DONE, TERMINATE, CANCELED]:
            raise ValidationError({'status': 'invalid status choice'})

        status = CANCELED if status == TERMINATE else status

        valid_transitions = [
            (PENDING, PENDING),
            (PENDING, DONE),
            (PENDING, CANCELED),
            (PROCESS, DONE),
            (PROCESS, CANCELED),
        ]

        if manual_withdraw.status == status and status != PENDING:
            return manual_withdraw

        if (manual_withdraw.status, status) not in valid_transitions:
            raise ValidationError({'status': 'invalid status transition (%s -> %s)' % (manual_withdraw.status, status)})

        ManualWithdraw.objects.filter(id=manual_withdraw.id).update(trx_hash=validated_data.get('trx_hash'), status=status)

        return manual_withdraw


class ManualWithdrawUpdateView(CreateAPIView, UserPassesTestMixin):
    authentication_classes = [CustomTokenAuthentication]
    serializer_class = ManualWithdrawSerializer

    def test_func(self):
        permission_check = self.request.user.has_perm('ledger.change_transfer')
        return permission_check
