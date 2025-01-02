from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .asset import Asset
from .network import Network
from accounts.models import Account, User
from ledger.models.transfer import Transfer


class AddressBook(models.Model):
    history = HistoricalRecords()

    TYPES = TYPE_INTERNAL, TYPE_NETWORK = 'internal', 'network'

    type = models.CharField(
        max_length=8,
        choices=[(t, t) for t in TYPES],
        default=TYPE_NETWORK,
    )

    dest_user = models.ForeignKey(to=User, blank=True, null=True, on_delete=models.CASCADE, verbose_name='صاحب آدرس')
    name = models.CharField(max_length=100, verbose_name='نام')
    address = models.CharField(max_length=100, blank=True, verbose_name='آدرس')
    account = models.ForeignKey(to=Account, on_delete=models.CASCADE, verbose_name='حساب')
    network = models.ForeignKey(to=Network, null=True, blank=True, on_delete=models.CASCADE, verbose_name='شبکه')
    asset = models.ForeignKey(to=Asset, blank=True, null=True, on_delete=models.CASCADE, verbose_name='رمزارز')
    deleted = models.BooleanField(default=False)
    whitelist = models.BooleanField(default=False)
    memo = models.CharField(max_length=64, blank=True)

    @staticmethod
    def is_address_used_in_24h(address: str) -> bool:
        return Transfer.objects.filter(
            deposit=False,
            out_address=address,
            created__gte=timezone.now() - timedelta(days=1)
        ).exists()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'دفترچه آدرس‌ها'
        verbose_name_plural = 'دفترچه‌های آدرس'

        constraints = [
            models.CheckConstraint(
                check=Q(type='internal', dest_user__isnull=False) | ~Q(type='internal'),
                name='check_internal_requires_dest_user'
            ),
            models.CheckConstraint(
                check=Q(type='network', address__isnull=False, network__isnull=False) | ~Q(type='network'),
                name='check_network_requires_address_and_network'
            ),
        ]
