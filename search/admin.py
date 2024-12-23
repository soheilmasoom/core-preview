from django.contrib import admin

from _base.utils import admin_register_for_crypto_exchange
from search.models import SearchHistory


@admin_register_for_crypto_exchange(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'query', )
    readonly_fields = ('created', 'account', 'query', 'result')

