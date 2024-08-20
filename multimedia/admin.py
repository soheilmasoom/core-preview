from django import forms
from django.contrib import admin, messages
from django.db import models
from django.db.models import F
from django.utils.safestring import mark_safe
from typing import List
from simple_history.admin import SimpleHistoryAdmin

from accounts.admin_guard.html_tags import admin_page_anchor
from multimedia.utils.backoffice_content import BackofficeContent
from multimedia.models import Image, Banner, CoinPriceContent, Article, Section, File, Guide, GuideGroup
from markdown import markdown


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
    actions = ('create_content', 'update_content', 'get_content')

    def content_action(self, action, request, queryset : List[CoinPriceContent]):
        actions = {
            "create" : BackofficeContent().create_coin_content,
            "update" : BackofficeContent().update_coin_content,
            "get":  BackofficeContent().get_coin_content
        }
        for coin_price_content in queryset:
            try:
                if str(coin_price_content.asset.name):
                    status_code, resp = actions[action](str(coin_price_content.asset.name))
                    if status_code >= 300:
                        self.message_user(request, f"{resp['message']} خطایی رخ داد", level=messages.ERROR)
                        continue
                    if action == "get":
                        coin_price_content.content = markdown(resp["result"])
                        coin_price_content.save()
                else:
                    self.message_user(
                        request=request,
                        message=f"نام کوین {str(coin_price_content.asset)} موجود نیست. خطایی رخ داد",
                        level=messages.ERROR
                    )
            except Exception as e:
                self.message_user(
                    request=request,
                    message=f"{str(e)} خطایی رخ داد",
                    level=messages.ERROR
                )

    @admin.action(description='درخواست تولید محتوا', permissions=['change'])
    def create_content(self, request, queryset: List[CoinPriceContent]):
        self.content_action("create", request, queryset)

    @admin.action(description='به‌روزرسانی تولید محتوا', permissions=['change'])
    def update_content(self, request, queryset : List[CoinPriceContent]):
        self.content_action("update", request, queryset)

    @admin.action(description='دریافت تولید محتوا', permissions=['change'])
    def get_content(self, request, queryset : List[CoinPriceContent]):
        self.content_action("get", request, queryset)


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

    @admin.action(description='Refresh', permissions=['change'])
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


class GuidTabularInline(admin.TabularInline):
    fields = ('get_id', 'title', 'image', 'description', 'link', 'video')
    readonly_fields = ('get_id', )
    model = Guide
    extra = 1

    @admin.display(description="id")
    def get_id(self, guide: Guide):
        return admin_page_anchor(guide.id or '', guide)


@admin.register(GuideGroup)
class GuideGroupAdmin(SimpleHistoryAdmin):
    list_display = ('slug', 'title',)
    search_fields = ('slug', 'title',)

    inlines = (GuidTabularInline, )


@admin.register(Guide)
class GuidAdmin(SimpleHistoryAdmin):
    list_display = ('title', 'group', 'order')
    list_filter = ('group', )
    search_fields = ('title', )
    list_editable = ('order', )
