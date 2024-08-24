from django.db import models


class BaseReport(models.Model):
    created = models.DateTimeField(db_index=True)
    type = models.CharField(max_length=256)

    views = models.PositiveIntegerField()
    clicks = models.PositiveIntegerField()
    cost = models.PositiveIntegerField()

    class Meta:
        abstract = True


class AdsReport(BaseReport):
    utm_campaign = models.CharField(max_length=256)
    utm_term = models.CharField(max_length=256)
    campaign_id = models.PositiveIntegerField()
    ad_id = models.PositiveIntegerField()

    class Meta:
        unique_together = ('created', 'type', 'utm_campaign', 'utm_term', 'campaign_id', 'ad_id')


class CampaignPublisherReport(BaseReport):
    utm_campaign = models.CharField(max_length=256)
    utm_content = models.CharField(max_length=256)

    campaign_id = models.PositiveIntegerField()
    publisher_id = models.PositiveIntegerField()

    class Meta:
        unique_together = ('created', 'type', 'utm_campaign', 'utm_content', 'campaign_id', 'publisher_id')


class CampaignInfo(models.Model):
    title = models.CharField(max_length=256)

    utm_source = models.CharField(max_length=256)
    utm_medium = models.CharField(max_length=256)
    utm_campaign = models.CharField(max_length=256)

    campaign_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.title


class CampaignCost(models.Model):
    created = models.DateField()
    campaign = models.ForeignKey(CampaignInfo, on_delete=models.CASCADE)
    cost = models.PositiveIntegerField()

    class Meta:
        unique_together = ('created', 'campaign')
