from django.contrib import admin
from django.utils.safestring import mark_safe
from simple_history.admin import SimpleHistoryAdmin

from accounts.admin_guard.utils.html import get_table_html
from health.alert import ALERTS
from health.models import AlertType, AlertTrigger


@admin.register(AlertType)
class AlertTypeAdmin(admin.ModelAdmin):
    list_display = ('type', 'get_status', 'warning_threshold', 'error_threshold')
    readonly_fields = ('get_status', 'get_description', 'get_type_help', )
    ordering = ('id', )

    @admin.display(description='status', )
    def get_status(self, alert_type: AlertType):
        if not alert_type.id:
            return

        status = alert_type.get_status()

        colors = {status.OK: 'green', status.WARNING: 'darkorange', status.ERROR: 'red'}

        return mark_safe(f"<span style='color: {colors[status.type]}'>{status}</span>")

    @admin.display(description='type_help')
    def get_type_help(self, alert_type: AlertType):
        return mark_safe(get_table_html(['type', ('help', 'threshold help')], [{'type': a.NAME, 'help': a.HELP} for a in ALERTS.values()]))

    @admin.display(description='description')
    def get_description(self, alert_type: AlertType):
        if not alert_type.id:
            return

        status = alert_type.get_status()
        return status.description


@admin.register(AlertTrigger)
class AlertTriggerAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ('updated', 'alert_type', 'status', 'count')
    list_filter = ('alert_type', 'status')
