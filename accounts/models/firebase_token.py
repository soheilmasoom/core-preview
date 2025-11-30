from django.db import models

from accounts.models import User


class FirebaseToken(models.Model):

    created = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    token = models.CharField(max_length=256, unique=True)
    user_agent = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True)

    native_app = models.BooleanField(default=False)
