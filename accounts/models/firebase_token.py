from django.db import models

from accounts.models import User


class LiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(active=True)


class FirebaseToken(models.Model):
    objects = models.Manager()
    live_objects = LiveManager()

    created = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE, related_name='fcm_tokens')
    token = models.CharField(max_length=256, unique=True)
    user_agent = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    native_app = models.BooleanField(default=False)

    active = models.BooleanField(default=True, db_index=True)

    error = models.CharField(
        max_length=64,
        blank=True,
    )
