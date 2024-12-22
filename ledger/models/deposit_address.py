from django.conf import settings
from django.db import models

from accounts.models import Account
from ledger.models import Network
from ledger.models.address_key import AddressKey
from ledger.utils.blocklink import get_blocklink_requester


class DepositAddress(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    network = models.ForeignKey('ledger.Network', on_delete=models.PROTECT)
    address_key = models.ForeignKey('ledger.AddressKey', on_delete=models.PROTECT)
    address = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return '%s (network= %s)' % (self.address, self.network)

    @classmethod
    def get_deposit_address(cls, account: Account, network: Network):
        requester = get_blocklink_requester()
        architecture = requester.get_network_arch(network.symbol)

        address_key = AddressKey.objects.filter(account=account, architecture=architecture, deleted=False).first()

        if not address_key:
            tag = '{brand}-base-{account_id}'.format(brand=settings.BRAND_EN.lower(), account_id=account.id)
            address_dict = requester.create_wallet(arch=architecture, tag=tag).data

            address_key, _ = AddressKey.objects.get_or_create(
                account=account,
                architecture=architecture,
                deleted=False,
                defaults={
                    'address': address_dict.get('address'),
                    'public_address': address_dict.get('address'),
                    'memo': address_dict.get('memo') or ''
                }
            )

        deposit_address, _ = DepositAddress.objects.get_or_create(
            address_key=address_key,
            network=network,
            defaults={
                'address': address_key.public_address
            }
        )

        return deposit_address

    class Meta:
        unique_together = ('address_key', 'network')

        permissions = [
            ("list_depositaddress", "Can list deposit address"),
        ]
