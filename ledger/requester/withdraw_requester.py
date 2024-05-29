import requests
from decouple import config
from django.conf import settings


class RequestWithdraw:
    def __init__(self):
        self.header = {
            'Authorization': config('BLOCKLINK_TOKEN')
        }

    def withdraw_from_hot_wallet(self, receiver_address, amount, network, asset, transfer_id, memo=''):
        data = {
            'receiver_address': receiver_address,
            'amount': amount,
            'network': network,
            'coin': asset,
            'requester_id': transfer_id,  # todo: use transfer_id
            'memo': memo
        }

        url = settings.BLOCKLINK_BASE_URL + '/api/v1/withdraw/'

        return requests.post(data=data, url=url, headers=self.header, timeout=15)
