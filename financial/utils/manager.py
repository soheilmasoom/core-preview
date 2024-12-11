from django.db import models


class LiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted=False)

