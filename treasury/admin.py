from django.contrib import admin
from django.core.exceptions import ValidationError
from django.contrib import messages
from .models import Treasury, PreciousMetalChoices


@admin.register(Treasury)
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
                    raise ValidationError(f'A treasury for {obj.get_metal_type_display()} already exists')
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            messages.error(request, str(e))
            return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('metal_type',)
        return self.readonly_fields
