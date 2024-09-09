from django.contrib import admin

from search.models import SearchHistory


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'query', )
    readonly_fields = ('created', 'account', 'query', 'result')

