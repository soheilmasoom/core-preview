from typing import Union

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import models, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import EmailNotification
from accounts.utils.validation import get_jalali_now


class LoginActivity(models.Model):
    TABLET, MOBILE, PC, UNKNOWN = 'tablet', 'mobile', 'pc', 'unknown'
    DEVICE_TYPE = ((TABLET, TABLET), (MOBILE, MOBILE), (PC, PC), (UNKNOWN, UNKNOWN))

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    logout_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField()

    is_sign_up = models.BooleanField(default=False)

    user_agent = models.TextField(blank=True)
    device = models.CharField(blank=True, max_length=200)
    device_type = models.CharField(choices=DEVICE_TYPE, default=UNKNOWN, max_length=16)
    location = models.CharField(blank=True, max_length=200)
    os = models.CharField(blank=True, max_length=200)
    browser = models.CharField(blank=True, max_length=200)
    city = models.CharField(blank=True, max_length=256)
    country = models.CharField(blank=True, max_length=256)
    ip_data = models.JSONField(null=True, blank=True)

    native_app = models.BooleanField(default=False)

    session = models.OneToOneField(Session, null=True, blank=True, on_delete=models.SET_NULL)
    refresh_token = models.OneToOneField('accounts.RefreshToken', null=True, blank=True, on_delete=models.SET_NULL)

    @transaction.atomic
    def destroy(self):
        destroyed = False

        if self.session:
            self.session.delete()
            self.session = None
            destroyed = True

        if self.refresh_token:
            self.refresh_token.log_out()
            self.refresh_token.delete()
            self.refresh_token = None
            destroyed = True

        if not destroyed:
            return

        self.logout_at = timezone.now()
        self.save(update_fields=['logout_at', 'session', 'refresh_token'])

    @classmethod
    def from_request(cls,  request) -> Union['LoginActivity', None]:
        session = Session.objects.filter(session_key=request.session.session_key).first()

        if session:
            return cls.objects.filter(session=session).first()

        try:
            access_token = request.META.get('HTTP_AUTHORIZATION', " ").split(' ')[1]
            token = AccessToken(access_token)
            return LoginActivity.objects.filter(refresh_token_id=token.payload['refresh_id']).first()
        except Exception:
            pass

        return None

    @staticmethod
    def send_successful_login_message(login_activity):
        EmailNotification.send_by_template(
            recipient=login_activity.user,
            template='login_new_device',
            context={
                'now': get_jalali_now(),
                'country': login_activity.country,
                'city': login_activity.city,
                'ip': login_activity.ip,
                'brand': settings.BRAND,
                'site_url': settings.PANEL_URL
            }
        )

    @staticmethod
    def send_unsuccessful_login_message(user):
        EmailNotification.send_by_template(
            recipient=user,
            template='login_unsuccessful',
            check_spam=True,
            context={
                'now': get_jalali_now(),
                'brand': settings.BRAND,
                'site_url': settings.PANEL_URL
            }
        )

    class Meta:
        verbose_name_plural = verbose_name = "تاریخچه ورود به حساب"
        indexes = [
            models.Index(fields=['user', 'ip', 'browser', 'os'], name="login_activity_idx"),
            models.Index(fields=['user', 'device'], name='login_suspension_idx')
        ]

    def __str__(self):
        return f'{self.device} {self.os}'
