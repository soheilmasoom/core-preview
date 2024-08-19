from django.db import models
from simple_history.models import HistoricalRecords


class GuideGroup(models.Model):
    history = HistoricalRecords()

    title = models.CharField(max_length=256)
    slug = models.SlugField(max_length=256, unique=True, db_index=True)

    def __str__(self):
        return self.slug


class Guide(models.Model):
    history = HistoricalRecords()

    title = models.CharField(max_length=256)
    image = models.ImageField(upload_to='multimedia/guide/', null=True, blank=True)
    description = models.TextField(blank=True)
    link = models.URLField(blank=True)
    video = models.URLField(blank=True)

    order = models.PositiveSmallIntegerField(default=0)
    group = models.ForeignKey(GuideGroup, on_delete=models.CASCADE, related_name='guides')

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return self.title
