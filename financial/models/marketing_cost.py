from django.db import models


class MarketingSource(models.Model):
    utm_source = models.CharField(max_length=256)
    utm_medium = models.CharField(max_length=256, blank=True)
    utm_campaign = models.CharField(max_length=256, blank=True)
    utm_content = models.CharField(max_length=256, blank=True)
    utm_term = models.CharField(max_length=256, blank=True)

    class Meta:
        unique_together = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')

    def __str__(self):
        utms = [self.utm_source, self.utm_medium, self.utm_campaign, self.utm_content, self.utm_term]

        valid_index = 1

        while valid_index < len(utms):
            if not utms[valid_index]:
                break

            valid_index += 1

        return '/'.join(utms[:valid_index])


class MarketingCost(models.Model):
    source = models.ForeignKey(to=MarketingSource, on_delete=models.CASCADE)
    date = models.DateField()
    cost = models.PositiveIntegerField()

    class Meta:
        unique_together = ('date', 'source')

    def __str__(self):
        return '%s %s' % (self.source, self.date)
