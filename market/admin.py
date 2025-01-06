from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import F
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from accounts.admin_guard.admin import AdvancedAdmin
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


class AccountTradeFilter(SimpleListFilter):
    title = 'account'
    parameter_name = 'account'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        account_id = self.value()

        if account_id is not None:
            return queryset.filter(account_id=account_id)
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


class AccountOrderFilter(SimpleListFilter):
    title = 'account'
    parameter_name = 'account'

    def lookups(self, request, model_admin):
        return (1, 1),

    def queryset(self, request, queryset):
        account_id = self.value()

        if account_id is not None:
            return queryset.filter(wallet__account_id=account_id)
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
class OrderAdmin(AdvancedAdmin):
    track_admin_activity = True

    list_display = ('get_created', 'side', 'get_symbol', 'fill_type', 'status', 'price', 'amount')
    list_filter = (TypeFilter, AccountOrderFilter, 'side', 'fill_type', 'status', 'symbol')
    readonly_fields = [field.name for field in Order._meta.get_fields()]
    actions = ('cancel_order', )

    list_permission_exclude_filters = ('id', 'account', 'group_id', 'position')

    def get_queryset(self, request):
        return super(OrderAdmin, self).get_queryset(request).annotate(symbol_name=F('symbol__name'))

    def allow_list_view(self, request):
        return any(map(lambda f: request.GET.get(f), self.list_permission_exclude_filters))

    @admin.display(description='created', ordering='created')
    def get_created(self, order):
        return order.created.astimezone().strftime('%Y-%m-%d %H:%M:%S')

    @admin.display(description='symbol')
    def get_symbol(self, order):
        return order.symbol_name

    @admin.action(description='Cancel', permissions=['change'])
    def cancel_order(self, request, queryset):
        Order.cancel_orders(queryset.filter(status=Order.NEW))

    def _get_user(self, obj):
        if obj.account:
            return obj.account.user

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
class TradeAdmin(AdvancedAdmin):
    track_admin_activity = True

    list_display = ('get_created', 'get_symbol', 'side', 'price', 'is_maker', 'market',
                    'amount', 'fee_amount', 'fee_revenue')
    list_filter = ('trade_source', AccountTradeFilter, 'symbol', 'market')
    # readonly_fields = [field.name for field in Order._meta.get_fields()]
    actions = ('revert', )

    list_permission_exclude_filters = ('id', 'account', 'group_id', 'position')

    def get_queryset(self, request):
        return super(TradeAdmin, self).get_queryset(request).annotate(symbol_name=F('symbol__name'))

    def allow_list_view(self, request):
        return any(map(lambda f: request.GET.get(f), self.list_permission_exclude_filters)) \
               or request.GET.get('status') == 'new' or request.GET.get('status__exact') == 'new'

    @admin.display(description='created', ordering='created')
    def get_created(self, trade: Trade):
        return trade.created.astimezone().strftime('%Y-%m-%d %H:%M:%S')

    @admin.display(description='symbol')
    def get_symbol(self, trade):
        return trade.symbol_name

    @admin.action(description='Revert', permissions=['change'])
    def revert(self, request, queryset):
        for trade in queryset:
            trade.revert()

    def _get_user(self, obj):
        if obj.account:
            return obj.account.user

@admin.register(ReferralTrx)
class ReferralTrxAdmin(admin.ModelAdmin):
    list_display = ('created', 'referral', 'referrer_amount', 'trader_amount',)
    list_filter = ('referral', 'referral__owner')


@admin.register(StopLoss)
class StopLossAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_masked_wallet', 'symbol', 'fill_type', 'amount', 'filled_amount', 'trigger_price', 'price', 'side')
    readonly_fields = ('wallet', 'symbol', 'group_id', 'login_activity')
    search_fields = ('wallet__account__user__phone', 'symbol__name')
    actions = ('cancel',)

    @admin.display(description='wallet')
    def get_masked_wallet(self, stop_loss: StopLoss):
        return mark_safe(
            f'<span dir="ltr">{stop_loss.wallet}</span>'
        )

    @admin.action(description='Cancel', permissions=['change'])
    def cancel(self, request, queryset):
        for stop_loss in queryset:
            stop_loss.delete()


@admin.register(OCO)
class OCOAdmin(admin.ModelAdmin):
    list_display = ('created', 'wallet', 'symbol', 'amount', 'price', 'stop_loss_trigger_price', 'stop_loss_price', 'side')
    readonly_fields = ('wallet', 'symbol', 'group_id', 'login_activity')
