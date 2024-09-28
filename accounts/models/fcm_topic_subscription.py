from django.db import models
from accounts.models import User

class FCMTopicSubscription(models.Model):
    PENDING, DONE, FAIL = 'p', 'd', 'f'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    topic = models.CharField(max_length=255)
    action = models.CharField(max_length=50)
    status = models.CharField(
        choices=((PENDING, 'p'), (DONE, 'd'), (FAIL, 'f')),
        max_length=1,
        db_index=True,
        default=PENDING
    )

    def __str__(self):
        return f"{self.user.username} - {self.topic} - {self.status}"
