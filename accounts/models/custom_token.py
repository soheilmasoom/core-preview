from rest_framework.authtoken.models import Token
from django.contrib.postgres.fields import ArrayField
from django.db import models


class CustomToken(Token):
    SCOPES = WITHDRAW, TRADE = \
        'withdraw', 'trade'

    ip_list = ArrayField(
        models.GenericIPAddressField(default='127.0.0.1'), default=list, blank=True, null=True
    )
    scopes = ArrayField(
        models.CharField(choices=[(scope, scope) for scope in SCOPES], max_length=10), default=list([TRADE]), blank=True, null=True
    )

    throttle_exempted = models.BooleanField(default=False)

    def __str__(self):
        return str(self.user)
