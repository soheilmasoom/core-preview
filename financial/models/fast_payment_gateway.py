from django.db import models

from financial.utils.encryption import decrypt
from financial.utils.manager import LiveManager


class FastPaymentGateway(models.Model):
    TYPES = VANDAR = 'vandar'

    title = models.CharField(max_length=16)

    type = models.CharField(
        max_length=16,
        choices=[(t, t) for t in TYPES],
        default=VANDAR,
    )

    objects = models.Manager()
    live_objects = LiveManager()

    created = models.DateTimeField(auto_now_add=True)
    business_name = models.CharField(max_length=56)
    refresh_token_encrypted = models.CharField(max_length=4096, blank=True)

    priority = models.SmallIntegerField(default=0)
    active = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('priority',)

    @property
    def refresh_token(self):
        return decrypt(self.refresh_token_encrypted)