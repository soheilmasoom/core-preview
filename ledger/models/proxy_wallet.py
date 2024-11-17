from django.db import models


class ProxyWallet(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    network = models.ForeignKey('ledger.Network', on_delete=models.PROTECT)
    address = models.CharField(max_length=256, unique=True)
    comment = models.TextField(blank=True)

    def __str__(self):
        return f'{self.address},{self.network.symbol}'
