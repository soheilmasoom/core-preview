from django.contrib import admin
from django.core.exceptions import ValidationError
from django.contrib import messages

from _base.utils import admin_register_for_precious_metals_exchange
from .models import Treasury, PhysicalWithdraw


@admin_register_for_precious_metals_exchange(Treasury)
class TreasuryAdmin(admin.ModelAdmin):
    list_display = ('metal_type', 'current_balance', 'sold_amount', 'bank_reserved', 'last_updated')
    readonly_fields = ('last_updated',)
    actions = ['delete_selected']

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return True

    def save_model(self, request, obj, form, change):
        try:
            if not change:
                existing = Treasury.objects.filter(metal_type=obj.metal_type).exists()
                if existing:
                    raise ValidationError(f'خزانه {obj.get_metal_type_display()} قبلاً ایجاد شده است')
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            messages.error(request, str(e))
            return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('metal_type',)
        return self.readonly_fields


@admin_register_for_precious_metals_exchange(PhysicalWithdraw)
class PhysicalWithdrawAdmin(admin.ModelAdmin):
    list_display = ('account', 'asset', 'amount', 'status', 'created_at')
    readonly_fields = ('account', 'asset', 'amount', 'lock_id', 'created_at', 'updated_at')
    list_filter = ('status', 'asset')
    actions = ['approve_withdrawals', 'reject_withdrawals', 'complete_withdrawals']
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def approve_withdrawals(self, request, queryset):
        success = 0
        failed = 0
        for withdraw in queryset:
            try:
                withdraw.approve()
                success += 1
            except ValueError as e:
                messages.error(request, f'تایید دریافت {withdraw.id} با خطا مواجه شد: {str(e)}')
                failed += 1

        if success:
            messages.success(request, f'{success} دریافت فیزیکی با موفقیت تایید شد')
        if failed:
            messages.error(request, f'تایید {failed} دریافت فیزیکی با خطا مواجه شد')

    approve_withdrawals.short_description = "تایید دریافت فیزیکی"

    def reject_withdrawals(self, request, queryset):
        success = 0
        failed = 0
        for withdraw in queryset:
            try:
                withdraw.reject()
                success += 1
            except ValueError as e:
                messages.error(request, f'رد دریافت فیزیکی {withdraw.id} با خطا مواجه شد: {str(e)}')
                failed += 1

        if success:
            messages.success(request, f'{success} دریافت فیزیکی با موفقیت رد شد')
        if failed:
            messages.error(request, f'رد {failed} دریافت فیزیکی با خطا مواجه شد')

    reject_withdrawals.short_description = "رد درخواست"

    def complete_withdrawals(self, request, queryset):
        success = 0
        failed = 0
        for withdraw in queryset:
            try:
                withdraw.complete()
                success += 1
            except ValueError as e:
                messages.error(request, f'تکمیل دریافت فیزیکی {withdraw.id} با خطا مواجه شد: {str(e)}')
                failed += 1

        if success:
            messages.success(request, f'{success} دریافت فیزیکی با موفقیت تحویل داده شد')
        if failed:
            messages.error(request, f'تکمیل {failed} دریافت فیزیکی با خطا مواجه شد')

    complete_withdrawals.short_description = "تحویل داده شده"

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions