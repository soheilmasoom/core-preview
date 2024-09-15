from django.conf import settings
from django.db import models

from accounts.utils.random import get_random_str


class AttributionTracker(models.Model):
    TYPES = YANDEX, METRIX = 'yandex', 'metrix'

    YANDEX_FIELDS = {
        'profile_id': 'profile_id',
        'google_aid': 'gps_adid',
        'app_package_name': 'app_id',
        'install_datetime': 'installed_at',
        'click_datetime': 'clicked_at',
        'install_ipv6': 'install_ip',
        'device_type': 'device_type',
        'device_manufacturer': 'device_manufacturer',
        'device_model': 'device_model',
        'device_locale': 'device_locale',
        'os_name': 'os_name',
        'os_version': 'os_version',
        'appmetrica_device_id': 'device_id',
        'country_iso_code': 'country',
        'operator_name': 'operator',
        'click_url_parameters': 'click_url_params',
    }

    name = models.CharField(max_length=64)
    type = models.CharField(max_length=8, choices=[(t, t) for t in TYPES])
    key = models.CharField(max_length=8, default=get_random_str, unique=True)

    def __str__(self):
        return self.name

    def get_postback_link(self):
        if self.id:
            fields = "&".join(["%s={%s}" % (field, tracker_field) for tracker_field, field in self.YANDEX_FIELDS.items()])
            return f'{settings.HOST_URL}/api/v1/accounts/attribution/?key={self.key}&{fields}'


class AppConfig(models.Model):
    package_name = models.CharField(max_length=256, unique=True)
    default = models.BooleanField(default=True)

    yandex_api_key = models.CharField(max_length=64, unique=True)
    yandex_app_id = models.CharField(max_length=64, unique=True)

    @classmethod
    def get_by_package_name(cls, package_name: str) -> 'AppConfig':
        app = AppConfig.objects.filter(package_name=package_name).first()
        if app:
            return app

        return AppConfig.objects.filter(default=True).order_by('id').first()


class Attribution(models.Model):
    DEVICES = PHONE, TABLET, PHABLET, TV = 'PHONE', 'TABLET', 'PHABLET', 'TV'

    created = models.DateTimeField(auto_now_add=True)

    tracker = models.ForeignKey(AttributionTracker, on_delete=models.CASCADE)

    profile_id = models.CharField(max_length=64, blank=True, db_index=True)
    gps_adid = models.CharField(max_length=64, blank=True, db_index=True)
    app_id = models.CharField(max_length=64, blank=True)

    installed_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)

    install_ip = models.GenericIPAddressField(null=True, blank=True)

    device_type = models.CharField(max_length=8, blank=True, choices=[(d, d) for d in DEVICES])
    device_manufacturer = models.CharField(max_length=64, blank=True)
    device_model = models.CharField(max_length=64, blank=True)
    device_locale = models.CharField(max_length=64, blank=True)

    os_name = models.CharField(max_length=64, blank=True)
    os_version = models.CharField(max_length=64, blank=True)

    device_id = models.CharField(max_length=64, blank=True)

    country = models.CharField(max_length=64, blank=True)
    operator = models.CharField(max_length=64, blank=True)

    click_url_params = models.CharField(max_length=256, blank=True)

    @property
    def utm_medium(self):
        return self.tracker.type

    @property
    def utm_campaign(self):
        return self.tracker.key

    @property
    def utm_content(self):
        return self.tracker.name
