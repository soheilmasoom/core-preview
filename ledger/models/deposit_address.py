from django.db import models

from accounts.models import Account
from ledger.models import Network
from ledger.models.address_key import AddressKey
from ledger.utils.blocklink import get_blocklink_requester


class DepositAddress(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    network = models.ForeignKey('ledger.Network', on_delete=models.PROTECT)
    address = models.CharField(max_length=256, blank=True)
    address_key = models.ForeignKey('ledger.AddressKey', on_delete=models.PROTECT)

    def __str__(self):
        return '%s (network= %s)' % (self.address, self.network)

    @classmethod
    def get_deposit_address(cls, account: Account, network: Network):
        requester = get_blocklink_requester()
        architecture = requester.get_network_arch(network.symbol)

        address_key = AddressKey.objects.filter(account=account, architecture=architecture, deleted=False).first()

        if not address_key:
            address_dict = requester.create_wallet(account, architecture).data

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

        deposit_address = DepositAddress.objects.filter(address_key=address_key, network=network).first()

        if not deposit_address:
            deposit_address = DepositAddress.objects.create(
                network=network,
                address_key=address_key,
                address=address_key.public_address,
            )

        return deposit_address

    class Meta:
        unique_together = ('address_key', 'network', 'address')

        permissions = [
            ("list_depositaddress", "Can list deposit address"),
        ]
