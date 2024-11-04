from django.db import models

from accounts.models import User


class TrafficSource(models.Model):
    SIGNUP_SOURCES = MAIN, WIDGET = 'main', 'widget'

    created = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='کاربر', related_name='traffic_source')

    utm_source = models.CharField(max_length=256, blank=True)
    utm_medium = models.CharField(max_length=256, blank=True)
    utm_campaign = models.CharField(max_length=256, blank=True)
    utm_content = models.CharField(max_length=256, blank=True)
    utm_term = models.CharField(max_length=256, blank=True)
    gps_adid = models.CharField(max_length=256, blank=True)
    yandex_profile_id = models.CharField(max_length=256, blank=True)
    package_name = models.CharField(max_length=256, blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)

    signup_source = models.CharField(
        max_length=8,
        default=MAIN,
        choices=[(s, s) for s in SIGNUP_SOURCES]
    )

    def __str__(self):
        return f'User {self.user.id}: {self.utm_source}/{self.utm_medium}'
