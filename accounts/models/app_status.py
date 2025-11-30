from django.db import models
from simple_history.models import HistoricalRecords


class AppStatus(models.Model):
    active = models.BooleanField(default=True)
    latest_version = models.PositiveIntegerField(default=1)
    force_update_version = models.PositiveIntegerField(default=0)

    apk_link = models.FileField(null=True, blank=True, upload_to='app/')

    history = HistoricalRecords()

    @classmethod
    def get_active(cls) -> 'AppStatus':
        return AppStatus.objects.filter(active=True).first() or AppStatus()

    class Meta:
        verbose_name = verbose_name_plural = 'وضعیت اپلیکیشن'
