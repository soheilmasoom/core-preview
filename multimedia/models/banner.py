from django.db import models

from multimedia.storage import PublicMediaStorage


class Banner(models.Model):
    ONLY_DESKTOP = 'only_desktop'

    title = models.CharField(max_length=64)
    image = models.ImageField(storage=PublicMediaStorage(), upload_to='banners/')
    link = models.CharField(max_length=256)
    app_link = models.CharField(max_length=256, blank=True)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField()

    limit = models.CharField(
        max_length=16,
        blank=True,
        choices=((ONLY_DESKTOP, ONLY_DESKTOP),)
    )

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('order',)
