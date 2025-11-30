from django.db import models
from django.db.models import Q


class ReportPermission(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    utm_source = models.CharField(max_length=256, blank=True)
    utm_medium = models.CharField(max_length=256, blank=True)
    enable = models.BooleanField(default=True)

    @property
    def q(self):
        q = Q()
        if self.utm_source:
            q = q & Q(utm_source=self.utm_source)
        if self.utm_medium:
            q = q & Q(utm_medium=self.utm_medium)

        return q
