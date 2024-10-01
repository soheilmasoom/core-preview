from django.db import models

from accounts.utils.validation import PHONE_MAX_LENGTH


class SpamPhone(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    phone = models.CharField(
        max_length=PHONE_MAX_LENGTH,
        unique=True
    )
