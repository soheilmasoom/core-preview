from django.contrib import admin
from .models import Highlight, Story, StoryView


class StoryInline(admin.TabularInline):
    model = Story
    fields = ('order', 'media', 'text')
    ordering = ('order',)
    extra = 1


@admin.register(Highlight)
class HighlightAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title',)
    inlines = [StoryInline]


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ('highlight', 'order', 'text')
    list_filter = ('highlight',)
    search_fields = ('text',)
