import logging

from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from accounts.models import LoginActivity
from ledger.utils.external_price import BUY
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import CancelRequest, Order, StopLoss

logger = logging.getLogger(__name__)


class CancelRequestSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='order_id', required=False)
    client_order_id = serializers.CharField(write_only=True, required=False)
    canceled_at = serializers.CharField(source='created', read_only=True)

    @staticmethod
    def cancel_order(order: Order, validated_data, request):
        login_activity = LoginActivity.from_request(request)
        try:
            with transaction.atomic():
                req, created = CancelRequest.objects.get_or_create(
                    order_id=order.id,
                    defaults={'login_activity': login_activity}
                )

                if created:
                    order.cancel()
        except Exception as e:
            logger.error('failed canceling order', extra={'exp': e, 'order': validated_data})
            if settings.DEBUG_OR_TESTING_OR_STAGING:
                raise e
            raise APIException(_('Could not cancel order'))
        return req

    def create(self, validated_data):
        instance_id = validated_data.pop('order_id', None)
        client_order_id = None
        if not instance_id:
            client_order_id = validated_data.pop('client_order_id', None)
        if not (instance_id or client_order_id):
            raise NotFound(_('Order id is missing in input'))

        if instance_id and instance_id.startswith('sl-'):
            stop_loss = StopLoss.open_objects.filter(
                wallet__account=self.context['account'],
                id=instance_id.split('sl-')[1],
            ).first()

            if not stop_loss:
                raise NotFound(_('StopLoss not found'))

            if stop_loss.wallet.is_for_strategy and not self.context['allow_cancel_strategy_orders']:
                raise PermissionDenied({'message': _('You do not have permission to perform this action.'), })

            with WalletPipeline() as pipeline:
                stop_loss.delete()
                order = stop_loss.order_set.first()
                if order:
                    return self.cancel_order(order, validated_data, request=self.context['request'])
                else:
                    if stop_loss.price:
                        order_price = stop_loss.price
                    else:
                        conservative_factor = Decimal('1.01') if stop_loss.side == BUY else Decimal(1)
                        order_price = stop_loss.trigger_price * conservative_factor

                    release_amount = Order.get_to_lock_amount(
                        stop_loss.unfilled_amount, order_price, stop_loss.side, stop_loss.wallet.market
                    )
                    pipeline.release_lock(key=stop_loss.group_id, amount=release_amount)
                    # faking cancel request creation
                    return CancelRequest(order_id=instance_id, created=timezone.now())
        else:
            if instance_id:
                order_filter = {'id': instance_id}
            else:
                order_filter = {'client_order_id': client_order_id}
            order = Order.open_objects.filter(
                account=self.context['account'],
                **order_filter
            ).first()
            if not order or order.stop_loss:
                raise NotFound(_('Order not found'))
            if order.wallet.is_for_strategy and not self.context['allow_cancel_strategy_orders']:
                raise PermissionDenied({'message': _('You do not have permission to perform this action.'), })

        return self.cancel_order(order, validated_data, request=self.context['request'])

    class Meta:
        model = CancelRequest
        fields = ('id', 'canceled_at', 'client_order_id')


class BulkCancelRequestSerializer(serializers.Serializer):
    id_list = serializers.ListField(
        child=serializers.IntegerField(min_value=0),
        required=False
    )
    client_order_id_list = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
