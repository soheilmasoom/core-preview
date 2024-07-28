import requests
from django.conf import settings


class AddressRequester:
    def __init__(self):
        self.base_url = settings.BLOCKLINK_BASE_URL
        self.header = {
            'Authorization': settings.BLOCKLINK_TOKEN
        }

    def create_wallet(self, account, architecture):
        data = {
            'architecture': architecture,
            'tag': '{brand}-base-{account_id}'.format(
                brand=settings.BRAND_EN.lower(),
                account_id=account.id,
            )
        }
        url = self.base_url + '/api/v1/tracker/wallets/'
        return requests.post(url=url, data=data, headers=self.header, timeout=30).json()

    def refresh_solana_transactions(self, address, architecture):
        assert architecture == 'SOL'

        data = {
            'architecture': architecture,
            'pointer_address': address
        }
        url = self.base_url + '/api/v1/tracker/address/update/'
        return requests.put(url=url, data=data, headers=self.header, timeout=30).json()
