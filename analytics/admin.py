from django.contrib import admin

from analytics.models import ActiveTrader, EventTracker, ReportPermission


@admin.register(ActiveTrader)
class DailyAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('created', 'period', 'active', 'churn', 'new')


@admin.register(EventTracker)
class DailyAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('created', 'type', 'last_id')


@admin.register(ReportPermission)
class ReportPermissionAdmin(admin.ModelAdmin):
    list_display = ('created', 'user', 'utm_source', 'utm_medium', 'enable')
    raw_id_fields = ('user',)
    list_filter = ('enable', )
    list_editable = ('enable', )
