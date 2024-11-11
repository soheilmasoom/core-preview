import operator
from functools import reduce

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.safestring import mark_safe
from simple_history.admin import SimpleHistoryAdmin

from accounting.models import Account, AccountTransaction, TransactionAttachment, Vault, VaultItem, ReservedAsset, \
    AssetPrice, TradeRevenue, PeriodicFetcher, BlocklinkIncome, BlocklinkDustCost, TempCredit
from accounting.models.provider_income import ProviderIncome
from gamify.utils import clone_model
from ledger.utils.precision import humanize_number


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'iban', 'get_balance', 'create_vault')
    readonly_fields = ('get_balance', )
    list_filter = ('create_vault', )
    ordering = ('-create_vault', )

    @admin.display(description='موجودی')
    def get_balance(self, account: Account):
        return humanize_number(account.get_balance())


class TransactionAttachmentTabularInline(admin.TabularInline):
    fields = ('created', 'type', 'file')
    readonly_fields = ('created', )
    model = TransactionAttachment
    extra = 1


@admin.register(AccountTransaction)
class AccountTransactionAdmin(admin.ModelAdmin):
    fields = ('account', 'amount', 'get_amount', 'reason', 'type')
    list_display = ('created', 'account', 'get_amount', 'type', 'reason')
    readonly_fields = ('created', 'get_amount')
    inlines = (TransactionAttachmentTabularInline, )
    list_filter = ('account__name', 'type', 'account')
    actions = ('clone_trx', )
    search_fields = ('reason', )

    @admin.display(description='مقدار', ordering='amount')
    def get_amount(self, trx: AccountTransaction):
        return trx.amount and humanize_number(trx.amount)

    @admin.action(description='Clone', permissions=['change'])
    def clone_trx(self, request, queryset):
        for trx in queryset:
            clone_model(trx)


@admin.register(Vault)
class VaultAdmin(admin.ModelAdmin):
    list_display = ('name', 'market', 'type', 'get_usdt', 'get_value', 'real_value', 'expected_max_value',
                    'should_be_updated')
    ordering = ('-real_value', )
    list_filter = ('market', 'type', 'should_be_updated')
    list_editable = ('expected_max_value', 'should_be_updated')

    @admin.display(description='usdt')
    def get_usdt(self, vault: Vault):
        item = VaultItem.objects.filter(vault=vault, coin='USDT').first()

        if not item:
            return 0
        else:
            return item.balance

    @admin.display(description='value')
    def get_value(self, vault: Vault):
        return VaultItem.objects.filter(vault=vault).aggregate(sum=Sum('value_usdt'))['sum'] or 0


@admin.register(VaultItem)
class VaultItemAdmin(SimpleHistoryAdmin):
    list_display = ('coin', 'vault', 'balance', 'free', 'value_usdt', 'value_irt', 'expected_min_balance', 'updated')
    search_fields = ('coin', 'vault__name')
    list_filter = ('vault__name', 'vault__type', 'vault__market')
    ordering = ('-value_usdt', )
    readonly_fields = ('value_usdt', 'value_irt')
    list_editable = ('expected_min_balance', )

    def save_model(self, request, obj: VaultItem, form, change):
        obj.updated = timezone.now()
        super(VaultItemAdmin, self).save_model(request, obj, form, change)
        obj.vault.update_real_value(timezone.now())

    def get_search_results(self, request, queryset, search_term):
        if search_term:
            # Fields that need exact matching
            exact_fields = ['coin']

            orm_lookups = []
            for search_field in self.search_fields:
                if search_field in exact_fields:
                    orm_lookup = '{}__exact'.format(search_field)
                else:
                    orm_lookup = '{}__icontains'.format(search_field)

                orm_lookups.append(orm_lookup)

            # Build Q objects
            or_queries = [Q(**{orm_lookup: search_term}) for orm_lookup in orm_lookups]

            # Combine queries with OR
            queryset = queryset.filter(reduce(operator.or_, or_queries))
        else:
            queryset = queryset.all()

        return queryset, False


@admin.register(ReservedAsset)
class ReservedAssetAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ('coin', 'amount', 'updated', 'value_usdt', 'value_irt')
    search_fields = ('coin', )


@admin.register(AssetPrice)
class AssetPriceAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ('coin', 'price', 'updated')
    search_fields = ('coin', )


class GapFilledFilter(SimpleListFilter):
    title = "gap filled"
    parameter_name = "gap_filled"

    def lookups(self, request, model_admin):
        return (1, 'بله'), (0, 'خیر')

    def queryset(self, request, queryset):
        value = self.value()
        if value is not None:
            queryset = queryset.filter(gap_revenue__isnull=value == '0')

        return queryset


@admin.register(TradeRevenue)
class TradeRevenueAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = (
        'created', 'symbol', 'source', 'get_account', 'side', 'amount', 'price', 'value', 'gap_revenue', 'fee_revenue',
        'coin_price', 'coin_filled_price', 'hedge_key', 'value_is_fake')

    search_fields = ('group_id', 'hedge_key', 'symbol__name', )
    list_filter = (GapFilledFilter, 'symbol', 'source',)
    readonly_fields = ('account', 'symbol', 'group_id', 'login_activity', 'gap_revenue', 'fee_revenue')
    actions = ('zero_gap_revenue', )

    @admin.action(description='Zero Gap Revenue', permissions=['change'])
    def zero_gap_revenue(self, request, queryset):
        queryset.filter(gap_revenue__isnull=True).update(gap_revenue=0)

    @admin.display(description='account')
    def get_account(self, trade_revenue: TradeRevenue):
        return mark_safe(
            f'<span dir="ltr">{trade_revenue.account}</span>'
        )


@admin.register(ProviderIncome)
class BinanceIncomeAdmin(admin.ModelAdmin):
    list_display = ('income_date', 'income_type', 'income', 'coin', 'symbol')
    search_fields = ('symbol', 'coin')
    list_filter = ('income_type', )
    ordering = ('-income_date', 'income_type')


@admin.register(PeriodicFetcher)
class PeriodicFetcherAdmin(admin.ModelAdmin):
    list_display = ('name', 'end')


@admin.register(BlocklinkIncome)
class BlocklinkIncomeAdmin(admin.ModelAdmin):
    list_display = ('start', 'network', 'coin', 'real_fee_amount', 'fee_cost', 'fee_income',)
    list_filter = ('network', )
    search_fields = ('network', 'coin')


@admin.register(BlocklinkDustCost)
class BlocklinkDustCostAdmin(admin.ModelAdmin):
    list_display = ('updated', 'network', 'amount', 'usdt_value',)


@admin.register(TempCredit)
class TempCreditAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ('get_username', 'asset', 'amount', 'get_amount')
    ordering = ('user', 'asset')
    search_fields = ('user__phone', 'user__first_name', 'user__last_name', 'asset__symbol')
    list_editable = ('amount', )
    raw_id_fields = ('user', )

    @admin.display(description='user', ordering='user')
    def get_username(self, credit: TempCredit):
        return mark_safe(
            f'<span dir="ltr">{credit.user}</span>'
        )

    @admin.display(description='amount', ordering='amount')
    def get_amount(self, credit: TempCredit):
        return humanize_number(credit.amount)
