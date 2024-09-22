from datetime import datetime
from decimal import Decimal
from typing import Union
from uuid import UUID

from django.conf import settings
from django.db import models
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from simple_history.models import HistoricalRecords

from ledger.models import Wallet
from ledger.utils.fields import get_amount_field
from multimedia.storage import PublicMediaStorage


class InvalidAmount(Exception):
    pass


class LiveAssetManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(enable=True)


class Asset(models.Model):
    IRT = 'IRT'
    USDT = 'USDT'
    SHIB = 'SHIB'

    OTC_STATUSES = ACTIVE, DISABLED, BUY, SELL, COMING_SOON = 'active', 'disabled', 'buy', 'sell', 'soon'
    OTC_TRADE_ACTIVE_STATUSES = ACTIVE, BUY, SELL

    PRECISION = 8

    history = HistoricalRecords()

    objects = models.Manager()
    live_objects = LiveAssetManager()

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    name = models.CharField(max_length=32, unique=True)
    name_fa = models.CharField(max_length=32, blank=True)
    original_name_fa = models.CharField(max_length=32, blank=True)

    symbol = models.CharField(max_length=16, unique=True, db_index=True)
    original_symbol = models.CharField(max_length=16, blank=True)

    external_price_symbol = models.CharField(max_length=16, blank=True, db_index=True)

    trading_view_symbol = models.CharField(max_length=32, blank=True)

    logo = models.ImageField(blank=True, null=True, storage=PublicMediaStorage(), upload_to='coins/logo/')

    enable = models.BooleanField(default=False)
    order = models.SmallIntegerField(default=0, db_index=True)

    trend = models.BooleanField(default=False)
    pin_to_top = models.BooleanField(default=False)

    hedge = models.BooleanField(default=True)

    spread_category = models.ForeignKey('ledger.AssetSpreadCategory', on_delete=models.SET_NULL, null=True, blank=True)

    publish_date = models.DateTimeField(null=True, blank=True)

    otc_status = models.CharField(
        max_length=8,
        default=COMING_SOON,
        choices=[(s, s) for s in OTC_STATUSES],
    )

    price_page = models.BooleanField(default=True)

    price_alert_chanel_sensitivity = get_amount_field(null=True)

    distribution_factor = models.FloatField(default=0)

    stale_price = get_amount_field(null=True)

    margin_interest_fee = get_amount_field(default=Decimal('0.00015'))

    rebranded_to = models.OneToOneField('Asset', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ('-pin_to_top', '-trend', 'order',)

    def __str__(self):
        return self.symbol

    def get_precision(self):
        if self.symbol == Asset.IRT:
            return 0
        else:
            return Asset.PRECISION

    def get_wallet(self, account, market: str = Wallet.SPOT,
                   variant: Union[str, None, UUID] = None, expiration: datetime = None):
        assert market in Wallet.MARKETS
        from accounts.models import Account

        if isinstance(account, int):
            account_filter = {'account_id': account}

            if account in (settings.SYSTEM_ACCOUNT_ID, settings.OTC_ACCOUNT_ID, settings.MARKET_MAKER_ACCOUNT_ID,
                           settings.TRADER_ACCOUNT_ID, settings.REVERT_HELPER_ACCOUNT, settings.MARGIN_POOL_ACCOUNT,
                           settings.MARGIN_INSURANCE_ACCOUNT):
                account_type = Account.SYSTEM
            else:
                account_type = Account.ORDINARY

        elif isinstance(account, Account):
            account_filter = {'account': account}
            account_type = account.type

        else:
            raise NotImplementedError

        wallet, created = Wallet.objects.get_or_create(
            asset=self,
            market=market,
            variant=variant,
            **account_filter,
            defaults={
                'check_balance': account_type == Account.ORDINARY,
                'expiration': expiration,
            }
        )

        return wallet

    @property
    def otc_trade_active(self) -> bool:
        return self.otc_status in self.OTC_TRADE_ACTIVE_STATUSES

    @classmethod
    def get(cls, symbol: str):
        return Asset.objects.get(symbol=symbol)

    def is_cash(self):
        return self.symbol == self.IRT

    def is_trade_base(self):
        return self.symbol in (self.IRT, self.USDT)

    def get_original_symbol(self):
        return self.original_symbol or self.symbol

    def get_coin_multiplier(self) -> int:
        if not self.original_symbol or self.symbol == self.original_symbol:
            return 1
        elif self.symbol.startswith('1M-'):
            return 10 ** 6
        elif self.symbol.startswith('1000'):
            return 10 ** 3
        else:
            return 1


class AssetVariant(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return self.name


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ('symbol',)


class AssetSerializerMini(serializers.ModelSerializer):
    precision = serializers.SerializerMethodField()
    step_size = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    original_name_fa = serializers.SerializerMethodField()
    original_symbol = serializers.SerializerMethodField()

    def get_precision(self, asset: Asset):
        return asset.get_precision()

    def get_step_size(self, asset: Asset):
        return Asset.PRECISION

    def get_logo(self, asset: Asset):
        if asset.logo:
            return asset.logo.url

    def get_original_symbol(self, asset: Asset):
        return asset.get_original_symbol()

    def get_original_name_fa(self, asset: Asset):
        return asset.original_name_fa or asset.name_fa

    class Meta:
        model = Asset
        fields = ('id', 'symbol', 'precision', 'step_size', 'name', 'name_fa', 'logo', 'original_symbol',
                  'original_name_fa', 'trading_view_symbol', 'otc_status')


class CoinField(serializers.CharField):
    def to_representation(self, value: Asset):
        if value:
            return value.symbol

    def to_internal_value(self, data: str):
        if not data:
            return
        else:
            return get_object_or_404(Asset, symbol=data)
