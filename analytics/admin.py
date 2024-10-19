from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from analytics.models import ActiveTrader, EventTracker, ReportPermission, Symbol, SymbolPrice


@admin.register(ActiveTrader)
class DailyAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('created', 'period', 'active', 'churn', 'new')


@admin.register(EventTracker)
class DailyAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('created', 'type', 'last_id')


@admin.register(ReportPermission)
class ReportPermissionAdmin(admin.ModelAdmin):
    list_display = ('created', 'user', 'utm_source', 'utm_medium', 'enable', 'get_link')
    raw_id_fields = ('user',)
    list_filter = ('enable', )
    list_editable = ('enable', )
    readonly_fields = ('group_id', 'get_link')

    @admin.display(description='Link')
    def get_link(self, report: ReportPermission):
        url = reverse('marketing_reports', kwargs={
            'group_id': report.group_id
        })
        return format_html('<a href="{}">Report Link</a>', url)


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'source', 'market_id')


@admin.register(SymbolPrice)
class SymbolPriceAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'created', 'open', 'close', 'high', 'low')
    list_filter = ('symbol', )
    ordering = ('symbol', 'created')
