from django.db import models

from market.models import Order


class CancelRequest(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    order_id = models.PositiveIntegerField(unique=True)

    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)
