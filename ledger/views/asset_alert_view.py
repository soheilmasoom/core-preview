import logging

from django.db import transaction
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import RetrieveUpdateAPIView, get_object_or_404
from rest_framework.response import Response

from accounts.models import User
from accounts.utils.price_alert import subscribe_alert, unsubscribe_alert, subscribe_user_to_alerts, \
    unsubscribe_user_to_alerts
from ledger.models import AssetAlert, BulkAssetAlert, Asset
from ledger.models.asset import AssetSerializerMini, CoinField
from ledger.utils.coins_info import get_coins_info
from ledger.utils.dto import CoinInfo
from ledger.utils.external_price import SELL
from ledger.utils.precision import get_symbol_presentation_price
from ledger.utils.price import get_prices, get_coins_symbols, get_last_price
from ledger.views.coin_category_list_view import CoinCategorySerializer

logger = logging.getLogger(__name__)


class AssetAlertSerializer(serializers.ModelSerializer):
    coin = CoinField(source='asset', write_only=True)

    asset = AssetSerializerMini(read_only=True)
    price_usdt = serializers.SerializerMethodField()
    price_irt = serializers.SerializerMethodField()
    change_24h = serializers.SerializerMethodField()

    def get_change_24h(self, asset_alert: AssetAlert):
        return self.context['cap_info'].get(asset_alert.asset.symbol, CoinInfo()).change_24h

    def get_price_irt(self, asset_alert: AssetAlert):
        symbol = asset_alert.asset.symbol + Asset.IRT
        price = get_last_price(symbol)
        return get_symbol_presentation_price(symbol, price)

    def get_price_usdt(self, asset_alert: AssetAlert):
        symbol = asset_alert.asset.symbol + Asset.USDT
        price = get_last_price(symbol)
        return get_symbol_presentation_price(symbol, price)

    def create(self, validated_data):
        user = self.context['request'].user
        alert, _ = AssetAlert.objects.get_or_create(
            asset=validated_data['asset'],
            user=user
        )

        alert.activate()

        return alert

    class Meta:
        model = AssetAlert
        fields = ('id', 'coin', 'asset', 'price_usdt', 'price_irt', 'change_24h', 'active')
        read_only_fields = ('active',)


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
    serializer_class = AssetAlertSerializer

    def get_serializer_context(self):
        ctx = super(AssetAlertViewSet, self).get_serializer_context()

        return {
            **ctx,
            'cap_info': get_coins_info(),
        }

    def perform_destroy(self, alert: AssetAlert):
        alert.deactivate()

    def destroy(self, request, *args, **kwargs):
        if 'coin' in self.kwargs:  # remove destroy method after migration
            return super(AssetAlertViewSet, self).destroy(request, *args, **kwargs)

        serializer = AssetAlertSerializer(
            data=self.request.data,
            context={'request': self.request}
        )
        serializer.is_valid(raise_exception=True)
        asset = serializer.validated_data['asset']

        alert = AssetAlert.objects.filter(user=self.request.user, asset=asset).first()

        if alert:
            self.perform_destroy(alert)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        queryset = AssetAlert.live_objects.filter(user=self.request.user).prefetch_related('asset')
        coin = self.request.query_params.get('coin')

        if coin:
            queryset = queryset.filter(asset__symbol=coin)

        return queryset

    def get_object(self):
        asset = get_object_or_404(Asset, symbol=self.kwargs['coin'], enable=True)
        alert, _ = AssetAlert.objects.get_or_create(
            asset=asset,
            user=self.request.user
        )
        return alert


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
    def update(self, user: User, validated_data):
        new_state = validated_data['is_price_notif_on']
        AssetAlert.change_user_price_alerts(user, new_state)
        return user

    class Meta:
        model = User
        fields = ('is_price_notif_on',)


class PriceNotifSwitchView(RetrieveUpdateAPIView):
    serializer_class = PriceNotifSwitchSerializer

    def get_object(self):
        return self.request.user
