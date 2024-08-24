from datetime import timedelta

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
    list_display = ('created', 'campaign', 'cost_irt', 'cost_usdt')
    search_fields = ('campaign__utm_source', 'campaign__utm_medium', 'campaign__utm_campaign')
    list_filter = ('campaign', )
    ordering = ('-created', )
    actions = ('clone_for_next_days', )

    @admin.action(description='Clone for Next 3 Days', permissions=['view'])
    def clone_for_next_days(self, request, queryset):
        for campaign_cost in queryset:  # type: CampaignCost
            for i in range(3):
                CampaignCost.objects.get_or_create(
                    created=campaign_cost.created + timedelta(days=1 + i),
                    campaign=campaign_cost.campaign
                )
