from django import forms
from django.contrib import admin
from django.db import models
from django.db.models import F
from django.utils.safestring import mark_safe
from simple_history.admin import SimpleHistoryAdmin

from multimedia.models import Image, Banner, CoinPriceContent, Article, Section, File


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('created', 'uuid',)
    readonly_fields = ('uuid', 'get_selfie_image',)
    search_fields = ('uuid',)

    @admin.display(description='preview')
    def get_selfie_image(self, image: Image):
        return mark_safe("<img src='%s' width='200' height='200' />" % image.get_absolute_image_url())


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('created', 'uuid',)
    readonly_fields = ('uuid', )


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'image', 'link', 'app_link', 'order', 'active')
    list_editable = ('active', 'order')
    list_filter = ('active', )

    def save_model(self, request, obj, form, change):
        if Banner.objects.filter(order=obj.order).exclude(id=obj.id).exists():
            Banner.objects.filter(order__gte=obj.order).exclude(id=obj.id).update(order=F('order') + 1)

        return super(BannerAdmin, self).save_model(request, obj, form, change)


@admin.register(CoinPriceContent)
class CoinPriceContentAdmin(SimpleHistoryAdmin):
    list_display = ('id', 'asset')
    search_fields = ('asset__symbol', )


@admin.register(Article)
class ArticleAdmin(SimpleHistoryAdmin):
    list_display = ('title', 'title_en', 'parent', 'order', 'is_pinned')
    list_editable = ('order', 'is_pinned')
    list_filter = ('parent', 'is_pinned')
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 1})},
    }
    actions = ('refresh_article', )
    exclude = ('_content_html', '_content_text')
    readonly_fields = ('slug', )

    def save_model(self, request, obj: Article, form, change):
        obj.save()
        obj.refresh()

    @admin.action(description='Refresh')
    def refresh_article(self, request, queryset):
        for article in queryset:
            article.refresh()


@admin.register(Section)
class SectionAdmin(SimpleHistoryAdmin):
    list_display = ('title', 'slug', 'order', 'parent')
    list_editable = ('order', )
    list_filter = ('parent', )
    ordering = ('-parent', 'order', 'id')

    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 1})},
    }
