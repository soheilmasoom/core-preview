from django.db import models

from financial.utils.encryption import decrypt, encrypt
from financial.utils.manager import ActiveManager


class DirectDebitGateway(models.Model):
    TYPES = VANDAR, = 'vandar',

    type = models.CharField(
        max_length=16,
        choices=[(t, t) for t in TYPES],
        default=VANDAR,
    )

    created = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=False)
    priority = models.SmallIntegerField(default=0)

    title = models.CharField(max_length=16)

    objects = models.Manager()
    live_objects = ActiveManager()

    business_name = models.CharField(max_length=56)
    refresh_token_encrypted = models.CharField(max_length=4096, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('priority',)

    @property
    def refresh_token(self):
        return decrypt(self.refresh_token_encrypted)

    def set_refresh_token(self, new_token: str):
        self.refresh_token_encrypted = encrypt(new_token.strip())
        self.save(update_fields=['refresh_token_encrypted'])
