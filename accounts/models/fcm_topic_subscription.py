from django.db import models
from accounts.models import User
from ledger.utils.fields import get_status_field


class FCMTopicSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    topic = models.CharField(max_length=255)
    action = models.CharField(max_length=50)
    status = get_status_field()

    def __str__(self):
        return f"{self.user.username} - {self.topic} - {self.status}"
