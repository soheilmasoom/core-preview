from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from ledger.models import Asset, MarginPosition
from ledger.utils.precision import get_presentation_amount
from market.models import Order, Trade, PairSymbol, CancelRequest, ReferralTrx, StopLoss, OCO


class BaseAssetFilter(SimpleListFilter):                                           
    title = 'Base Asset'
    parameter_name = 'base_asset'

    def lookups(self, request, model_admin):
        assets = set([t for t in Asset.objects.filter(symbol__in=(Asset.USDT, Asset.IRT))])
        return zip(assets, assets)

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(base_asset__symbol=self.value())
        else:
            return queryset


class UserTradeFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(account__user=user)
        else:
            return queryset


@admin.register(PairSymbol)
class PairSymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'enable', 'custom_taker_fee', 'custom_maker_fee', 'tick_size', 'step_size',
                    'strategy_enable', 'margin_enable')
    list_editable = ('enable', 'strategy_enable', 'margin_enable')
    list_filter = ('enable', BaseAssetFilter,)
    readonly_fields = ('last_trade_time', 'last_trade_price')
    search_fields = ('name', )
    ordering = ('-enable', 'asset__order', 'base_asset__order')


class TypeFilter(SimpleListFilter):
    title = "type"
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return [
            (Order.ORDINARY, 'Only ordinary'),
            ('system', 'System Maker Orders'),
            ('all', 'All orders')
        ]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset.filter(type=Order.ORDINARY)
        if self.value() == 'system':
            return queryset.exclude(type=Order.ORDINARY)
        return queryset


class UserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return (1, 1),

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(wallet__account__user_id=user)
        else:
            return queryset


class OrderPositionFilter(admin.SimpleListFilter):
    title = _('Position')
    parameter_name = 'position'

    def lookups(self, request, model_admin):
        positions = MarginPosition.objects.all()
        return ((position.id, _(str(position))) for position in positions)

    def queryset(self, request, queryset):
        if not self.parameter_name in request.GET.keys():
            return None

        if self.value() is None:
            return Order.objects.all()

        return Order.objects.filter(position__id=self.value())


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('created', 'created_at_millis', 'type', 'symbol', 'side', 'fill_type', 'status', 'price', 'amount')
    list_filter = (TypeFilter, UserFilter, 'side', 'fill_type', 'status', 'symbol')
    readonly_fields = ('wallet', 'symbol', 'account', 'stop_loss', 'login_activity', 'position')
    actions = ('cancel_order', )

    def created_at_millis(self, instance):
        created = instance.created.astimezone()
        return created.strftime('%S.%f')[:-3]

    created_at_millis.short_description = 'Created Second'

    @admin.action(description='Cancel', permissions=['change'])
    def cancel_order(self, request, queryset):
        Order.cancel_orders(queryset.filter(status=Order.NEW))


@admin.register(CancelRequest)
class CancelRequestAdmin(admin.ModelAdmin):
    list_display = ('created', 'created_at_millis', 'order_id')
    readonly_fields = ('login_activity', )

    def created_at_millis(self, instance):
        created = instance.created.astimezone()
        return created.strftime('%S.%f')[:-3]

    created_at_millis.short_description = 'Created Second'


class TradePositionFilter(admin.SimpleListFilter):
    title = _('Position')
    parameter_name = 'position'

    def lookups(self, request, model_admin):
        positions = MarginPosition.objects.all()
        return ((position.id, _(str(position))) for position in positions)

    def queryset(self, request, queryset):
        if not self.parameter_name in request.GET.keys():
            return None

        if self.value() is None:
            return Trade.objects.all()

        return Trade.objects.filter(position__id=self.value())


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ('created', 'created_at_millis', 'account', 'symbol', 'side', 'price', 'is_maker', 'market',
                    'amount', 'fee_amount', 'fee_revenue', 'get_value_irt', 'get_value_usdt')
    list_filter = ('trade_source', UserTradeFilter, 'symbol', 'market')
    readonly_fields = ('symbol', 'order_id', 'account', 'login_activity', 'group_id', 'position')
    search_fields = ('symbol__name', )
    actions = ('revert', )

    def created_at_millis(self, instance):
        created = instance.created.astimezone()
        return created.strftime('%S.%f')[:-3]

    created_at_millis.short_description = 'Created Second'

    @admin.display(description='value irt', ordering='value_irt')
    def get_value_irt(self, trade: Trade):
        return get_presentation_amount(trade.irt_value)

    @admin.display(description='value usdt', ordering='value_usdt')
    def get_value_usdt(self, trade: Trade):
        return get_presentation_amount(trade.usdt_value)

    @admin.action(description='Revert', permissions=['change'])
    def revert(self, request, queryset):
        for trade in queryset:
            trade.revert()


@admin.register(ReferralTrx)
class ReferralTrxAdmin(admin.ModelAdmin):
    list_display = ('created', 'referral', 'referrer_amount', 'trader_amount',)
    list_filter = ('referral', 'referral__owner')


@admin.register(StopLoss)
class StopLossAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_masked_wallet', 'symbol', 'fill_type', 'amount', 'filled_amount', 'trigger_price', 'price', 'side')
    readonly_fields = ('wallet', 'symbol', 'group_id', 'login_activity')

    @admin.display(description='wallet')
    def get_masked_wallet(self, stop_loss: StopLoss):
        return mark_safe(
            f'<span dir="ltr">{stop_loss.wallet}</span>'
        )


@admin.register(OCO)
class OCOAdmin(admin.ModelAdmin):
    list_display = ('created', 'wallet', 'symbol', 'amount', 'price', 'stop_loss_trigger_price', 'stop_loss_price', 'side')
    readonly_fields = ('wallet', 'symbol', 'group_id', 'login_activity')
