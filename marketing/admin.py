from django.conf import settings
from django.contrib import admin

from marketing.models import AdsReport, CampaignPublisherReport, CampaignInfo, CampaignCost


@admin.register(AdsReport)
class AdsReportAdmin(admin.ModelAdmin):
    list_display = ('created', 'type', 'utm_campaign', 'utm_term', 'views', 'clicks', 'cost')
    list_filter = ('type', 'utm_campaign')
    search_fields = ('utm_term', )


@admin.register(CampaignPublisherReport)
class CampaignPublisherReportAdmin(admin.ModelAdmin):
    list_display = ('created', 'type', 'utm_campaign', 'utm_content', 'views', 'clicks', 'cost')
    list_filter = ('type', 'utm_campaign')
    search_fields = ('utm_content', )


@admin.register(CampaignInfo)
class CampaignInfoAdmin(admin.ModelAdmin):
    list_display = ('title', 'utm_source', 'utm_medium', 'utm_campaign', 'campaign_id')
    search_fields = ('title', 'campaign_id', 'utm_source', 'utm_medium', 'utm_campaign')
    list_filter = ('utm_source', 'utm_medium', 'utm_campaign')


@admin.register(CampaignCost)
class CampaignCostAdmin(admin.ModelAdmin):
    list_display = ('created', 'campaign', 'cost')
    search_fields = ('campaign__utm_source', 'campaign__utm_medium', 'campaign__utm_campaign')
    list_filter = ('campaign', )
    ordering = ('-created', )
