from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Sum
from django.utils.safestring import mark_safe

from accounts.models import User
from accounts.utils.admin import url_to_admin_list, url_to_edit_object
from ledger.utils.precision import get_presentation_amount
from .models import StakeRequest, StakeRevenue, StakeOption


@admin.register(StakeOption)
class StakeOptionAdmin(admin.ModelAdmin):
    list_display = ['asset', 'apr', 'get_stake_request_count', 'get_stake_request_amount', 'total_cap', 'fee', 'enable',
                    'landing']
    list_editable = ('enable', 'landing')
    readonly_fields = ('get_stake_request_count', 'get_stake_request_amount')
    list_filter = ('enable', )
    ordering = ('-enable', '-apr')

    def get_stake_request_count(self, stake_option: StakeOption):
        return StakeRequest.objects.filter(
            stake_option=stake_option,
            status__in=(StakeRequest.DONE, StakeRequest.PENDING, StakeRequest.PROCESS)
        ).count()
    get_stake_request_count.short_description = 'count'

    def get_stake_request_amount(self, stake_option: StakeOption):
        return StakeRequest.objects.filter(
            stake_option=stake_option,
            status__in=(StakeRequest.DONE, StakeRequest.PENDING, StakeRequest.PROCESS)
        ).aggregate(amount=Sum('amount'))['amount'] or 0
    get_stake_request_amount.short_description = 'sum'


class StakeStatusFilter(SimpleListFilter):
    title = 'نیازمند بررسی'
    parameter_name = 'check_need'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        status_filter = request.GET.get('check_need')
        if status_filter is not None:
            return queryset.exclude(status__in=[StakeRequest.DONE, StakeRequest.CANCEL_COMPLETE, StakeRequest.FINISHED])
        else:
            return queryset


@admin.register(StakeRequest)
class StakeRequestAdmin(admin.ModelAdmin):
    list_display = ['get_stake_option_asset', 'get_stake_option_apr', 'created', 'get_amount', 'get_user', 'status',
                    'start_at', 'cancel_request_at', 'cancel_pending_at', 'end_at', 'get_stake_revenue']
    actions = ('stake_request_processing', 'stake_request_done',
               'stake_request_cancel_processing', 'stake_request_cancel_done',)
    readonly_fields = ('get_stake_option_asset', 'account', 'status', 'stake_option', 'get_amount', 'amount',
                       'get_user', 'login_activity')
    list_filter = ('status', StakeStatusFilter)
    search_fields = ('account__user__phone', 'stake_option__asset__symbol')

    def get_stake_option_asset(self, stake_request: StakeRequest):
        return stake_request.stake_option.asset
    get_stake_option_asset.short_description = 'asset'

    def get_stake_revenue(self, stake_request: StakeRequest):
        return StakeRevenue.objects.filter(stake_request=stake_request).aggregate(Sum('revenue'))['revenue__sum']
    get_stake_revenue.short_description = 'Total Revenue'

    def get_stake_option_apr(self, stake_request: StakeRequest):
        return stake_request.stake_option.apr
    get_stake_option_apr.short_description = 'Plan APR'

    def get_amount(self, stake_request: StakeRequest):
        return get_presentation_amount(stake_request.amount)
    get_amount.short_description = 'amount'

    def get_user(self, stake_request: StakeRequest):
        user = stake_request.account.user
        link = url_to_edit_object(user)
        return mark_safe("<span dir=\"ltr\"> <a href='%s'>%s</a></span>" % (link, user))
    get_user.short_description = 'user'

    @admin.action(description='بردن به حالت در انتظار', permissions=['view'])
    def stake_request_processing(self, request, queryset):
        queryset = queryset.filter(status=StakeRequest.PROCESS)
        for stake_request in queryset:
            stake_request.change_status(StakeRequest.PENDING)

    @admin.action(description='بردن به حالت انجام شده', permissions=['view'])
    def stake_request_done(self, request, queryset):
        queryset = queryset.filter(status__in=[StakeRequest.PROCESS, StakeRequest.PENDING])
        for stake_request in queryset:
            stake_request.change_status(StakeRequest.DONE)

    @admin.action(description='بردن به حالت لغو در حال انجام', permissions=['view'])
    def stake_request_cancel_processing(self, request, queryset):
        queryset = queryset.filter(status__in=(StakeRequest.PROCESS, StakeRequest.PENDING, StakeRequest.CANCEL_PROCESS))
        for stake_request in queryset:
            stake_request.change_status(StakeRequest.CANCEL_PENDING)

    @admin.action(description='بردن به حالت لغو تکمیل شده', permissions=['view'])
    def stake_request_cancel_done(self, request, queryset):
        queryset = queryset.filter(status__in=(StakeRequest.CANCEL_PENDING, StakeRequest.CANCEL_PROCESS))
        for stake_request in queryset:
            stake_request.change_status(StakeRequest.CANCEL_COMPLETE)


@admin.register(StakeRevenue)
class StakeRevenueAdmin(admin.ModelAdmin):
    list_display = ['created', 'get_revenue', 'get_user', 'get_stake_option_asset', 'get_stake_option_apr']
    list_filter = ('stake_request__stake_option', )
    search_fields = ('stake_request__account__user__phone', )

    def get_revenue(self, stake_revenue: StakeRevenue):
        return get_presentation_amount(stake_revenue.revenue)

    def get_user(self, stake_revenue: StakeRevenue):
        user = stake_revenue.stake_request.account.user
        link = url_to_edit_object(user)
        return mark_safe("<span dir=\"ltr\"> <a href='%s'>%s</a></span>" % (link, user))
    get_user.short_description = 'user'

    def get_stake_option_apr(self, stake_revenue: StakeRevenue):
        return get_presentation_amount(stake_revenue.stake_request.stake_option.apr)
    get_stake_option_apr.short_description = 'apr'

    def get_stake_option_asset(self, stake_revenue: StakeRevenue):
        return stake_revenue.stake_request.stake_option.asset
    get_stake_option_asset.short_description = 'asset'
