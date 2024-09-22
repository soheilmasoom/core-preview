import logging
from django.db import transaction
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response

from accounts.models import User
from accounts.tasks.notification import manage_user_topic_subscription_task
from ledger.models import AssetAlert, BulkAssetAlert, Asset
from ledger.models.asset import AssetSerializerMini, CoinField
from ledger.models.asset_alert import BASE_ALERT_PACKAGE, PRICE_CHANGE_ALERT_TYPES, AlertTrigger
from ledger.utils.coins_info import get_coins_info
from ledger.utils.dto import CoinInfo
from ledger.utils.external_price import SELL
from ledger.utils.precision import get_symbol_presentation_price
from ledger.utils.price import get_prices, get_coins_symbols
from ledger.views.coin_category_list_view import CoinCategorySerializer
from accounts.utils.push_notif import manage_user_topic_subscription, send_push_notif
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)


class AssetAlertCreateSerializer(serializers.ModelSerializer):
    coin = CoinField(source='asset', required=False)
    is_conditional = serializers.BooleanField(required=False)
    base_asset = CoinField(source='asset', required=False)
    trigger_price = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    type = serializers.ChoiceField(choices=PRICE_CHANGE_ALERT_TYPES, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    remaining_alerts = serializers.SerializerMethodField(readonly=True)

    def validate(self, data):
        user = self.context['request'].user
        asset = data['asset']
        if not data.get('is_conditional'):
            if AssetAlert.objects.filter(user=user, asset=asset).exists():
                raise ValidationError({'asset': 'ارز دیجیتال انتخاب شده تحت‌نظر می‌باشد.'})
            if asset.is_cash():
                raise ValidationError({'asset': 'ارزدیجیتال انتخاب شده نباید تومان باشد.'})
        return data

    def get_topic(self):
        asset = self.validated_data.get('asset')
        return f"price_alerts_{asset.symbol.lower()}"

    def get_remaining_alerts(self, obj):
        user = self.context['request'].user
        asset = obj.asset
        active_alerts_count = AssetAlert.objects.filter(user=user, asset=asset, active=True).count()
        return max(0, 100 - active_alerts_count)

    class Meta:
        model = AssetAlert
        fields = ('coin', 'base_asset', 'trigger_price', 'type', 'description', 'remaining_alerts', 'is_conditional')


class AssetAlertDeleteSerializer(serializers.ModelSerializer):
    coin = CoinField(source='asset', required=False)

    def validate(self, data):
        user = self.context['request'].user
        asset = data['asset']
        if not AssetAlert.objects.filter(user=user, asset=asset).exists():
            raise ValidationError({'asset': 'ارز دیجیتال انتخاب شده تحت‌نظر نمی‌باشد.'})
        return data

    class Meta:
        model = AssetAlert
        fields = ('coin',)


class AssetAlertObjectSerializer(serializers.ModelSerializer):
    asset = AssetSerializerMini()
    is_conditional = serializers.BooleanField(required=False)
    base_asset = CoinField(source='asset', required=False)
    trigger_price = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    type = serializers.ChoiceField(choices=PRICE_CHANGE_ALERT_TYPES, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    remaining_alerts = serializers.SerializerMethodField(readonly=True)

    def get_remaining_alerts(self, obj):
        user = self.context['request'].user
        asset = obj.asset
        active_alerts_count = AssetAlert.objects.filter(user=user, asset=asset, active=True).count()
        return max(0, 100 - active_alerts_count)

    def get_change_24h(self, asset_alert: AssetAlert):
        return self.context['cap_info'].get(asset_alert.asset.symbol, CoinInfo()).change_24h

    def get_price_usdt(self, asset_alert: AssetAlert):
        price = self.context['prices'].get(asset_alert.asset.symbol + Asset.USDT, 0)
        return get_symbol_presentation_price(asset_alert.asset.symbol + Asset.USDT, price)

    def get_price_irt(self, asset_alert: AssetAlert):
        price = self.context['prices'].get(asset_alert.asset.symbol + Asset.IRT, 0)
        return get_symbol_presentation_price(asset_alert.asset.symbol + Asset.IRT, price)

    class Meta:
        model = AssetAlert
        fields = ('asset', 'price_usdt', 'price_irt', 'change_24h', 'base_asset', 'trigger_price', 'type', 'description', 'remaining_alerts', 'is_conditional')


class BulkAssetAlertViewSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        user = self.context['request'].user
        subscription_type = attrs['subscription_type']

        if subscription_type == BulkAssetAlert.CATEGORY_COIN_CATEGORIES:
            coin_category = attrs.get('coin_category', None)
            if not coin_category:
                raise ValidationError({'coin_category': 'دسته بندی انتخاب نشده است.'})
        else:
            coin_category = None
        attrs['coin_category'] = coin_category
        if BulkAssetAlert.objects.filter(
                user=user,
                subscription_type=subscription_type,
                coin_category=coin_category
        ).exists():
            raise ValidationError({'bulk_asset': 'دسته بندی انتخاب شده تحت‌نظر می‌باشد.'})
        return attrs

    class Meta:
        model = BulkAssetAlert
        fields = ('subscription_type', 'coin_category',)
        extra_kwargs = {
            'coin_category': {'required': False, 'write_only': True},
        }


class BulkAssetAlertObjectSerializer(serializers.ModelSerializer):
    coin_category = CoinCategorySerializer()

    class Meta:
        model = BulkAssetAlert
        fields = ('subscription_type', 'coin_category',)


class AssetAlertViewSet(viewsets.ModelViewSet):
    serializer_class = AssetAlertCreateSerializer
    queryset = AssetAlert.objects.all().prefetch_related('asset')

    def create(self, request, *args, **kwargs):
        print("what")
        serializer = self.get_serializer(data=request.data, context={'request': request})
        print("what2")
        # serializer.is_valid(raise_exception=True)

        print("what3")
        user = request.user
        print("what4")
        asset_id = request.data.get('asset')

        if request.data.get('is_conditional'):
            active_alerts_count = AlertTrigger.objects.filter(user=user, asset_id=asset_id, active=True).count()

            if active_alerts_count >= 100:
                remaining_alerts = max(0, 100 - active_alerts_count)
                return Response({'detail': 'حداکثر ۱۰ هشدار برای هر ارز دیجیتال مجاز است.', 'remaining_alerts': remaining_alerts}, status=status.HTTP_400_BAD_REQUEST)
        else:
            topic = serializer.get_topic()
            manage_user_topic_subscription_task.delay(user.id, topic, 'subscribe')

        self.perform_create(serializer)
        response_data = serializer.data

        if request.data.get('is_conditional'):
            remaining_alerts = max(0, 100 - AlertTrigger.objects.filter(user=user, asset_id=asset_id, active=True).count())
            response_data['remaining_alerts'] = remaining_alerts

        return Response(response_data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = AssetAlertObjectSerializer(queryset, many=True, context={
            'request': request,
            'cap_info': get_coins_info(),
            'prices': get_prices(get_coins_symbols(queryset.values_list('asset__symbol', flat=True)), side=SELL, allow_stale=True)
        })
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        active_alerts_count = AlertTrigger.objects.filter(user=request.user, asset=instance.asset, active=True).count()
        remaining_alerts = max(0, 100 - active_alerts_count)
        return Response({'detail': 'هشدار قمیت حذف شد.', 'remaining_alerts': remaining_alerts}, status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        with transaction.atomic():
            user = self.request.user
            serializer = AssetAlertDeleteSerializer(data={'asset': instance.asset}, context={'request': self.request})
            serializer.is_valid(raise_exception=True)
            instance.delete()
            topic = serializer.get_topic()
            manage_user_topic_subscription_task.delay(user.id, topic, 'unsubscribe')

            logger.warning(f"destroy {topic}, {user}")

            if not (AssetAlert.objects.filter(user=user).exists() or BulkAssetAlert.objects.filter(user=user).exists()):
                user.is_price_notif_on = False
                user.save(update_fields=['is_price_notif_on'])

    def get_object(self):
        serializer = AssetAlertDeleteSerializer(
            data=self.request.data,
            context={'request': self.request}
        )
        serializer.is_valid(raise_exception=True)
        asset = serializer.validated_data.get('asset', None)
        user = self.request.user
        return self.get_queryset().get(user=user, asset=asset)

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user
        )

    def get_queryset(self):
        coin = self.request.query_params.get('coin')
        queryset = self.queryset.filter(user=self.request.user)

        if coin:
            queryset = queryset.filter(asset__symbol=coin)

        return queryset


class BulkAssetAlertViewSet(viewsets.ModelViewSet):
    serializer_class = BulkAssetAlertViewSerializer
    queryset = BulkAssetAlert.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = BulkAssetAlertObjectSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = BulkAssetAlertObjectSerializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user
        )

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class PriceNotifSwitchSerializer(serializers.ModelSerializer):
    is_price_notif_on = serializers.BooleanField()

    class Meta:
        model = User
        fields = ('is_price_notif_on',)


class PriceNotifSwitchView(RetrieveUpdateAPIView):
    serializer_class = PriceNotifSwitchSerializer

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()
            user = self.request.user
            if not AssetAlert.objects.filter(user=user).exists():
                for asset in Asset.objects.filter(symbol__in=BASE_ALERT_PACKAGE):
                    AssetAlert.objects.create(
                        user=user,
                        asset=asset
                    )
