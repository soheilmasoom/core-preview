from django.core.exceptions import ValidationError
from django.db import models

from ledger.utils.price import USDT_IRT, get_last_price


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

    utm_source = models.CharField(max_length=256, blank=True)
    utm_medium = models.CharField(max_length=256, blank=True)
    utm_campaign = models.CharField(max_length=256, blank=True)

    campaign_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('-id', )


class CampaignCost(models.Model):
    created = models.DateField()
    campaign = models.ForeignKey(CampaignInfo, on_delete=models.CASCADE)
    cost_irt = models.PositiveIntegerField(default=0)
    cost_usdt = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('created', 'campaign')

    def clean(self):
        if not self.cost_irt and not self.cost_usdt:
            raise ValidationError('No cost provided')

    def save(self, *args, **kwargs):
        if self.cost_irt and not self.cost_usdt:
            price = get_last_price(USDT_IRT) or 60_000
            self.cost_usdt = self.cost_irt / price

        elif not self.cost_irt and self.cost_usdt:
            price = get_last_price(USDT_IRT) or 60_000
            self.cost_irt = self.cost_usdt * price

        super(CampaignCost, self).save(*args, **kwargs)

    def __str__(self):
        return f'Cost {self.campaign} @ {self.created}'
