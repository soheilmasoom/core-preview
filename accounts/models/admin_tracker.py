from django.db import models

from accounts.models import User


class AdminTracker(models.Model):
    created = models.DateTimeField(auto_now_add=True, verbose_name="Timestamp")
    admin = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Admin User")
    model_name = models.CharField(max_length=255, verbose_name="Model Accessed")
    object_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="Object ID")
    url = models.CharField(max_length=1024, verbose_name="URL Accessed")

    def __str__(self):
        return f"{self.admin} {self.model_name} at {self.created}"
