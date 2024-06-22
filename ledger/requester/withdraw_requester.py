import requests
from decouple import config
from django.conf import settings

from ledger.models import ManualWithdraw


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
            'requester_id': transfer_id,
            'memo': memo
        }

        url = settings.BLOCKLINK_BASE_URL + '/api/v1/withdraw/'

        return requests.post(data=data, url=url, headers=self.header, timeout=15)

    def manual_withdraw_transfer(self, manual_withdraw: ManualWithdraw):
        assert manual_withdraw.triggered is False

        data = {
            'receiver_address': manual_withdraw.receiver_address,
            'amount': manual_withdraw.amount,
            'network': manual_withdraw.network.symbol,
            'coin': manual_withdraw.coin,
            'requester_id': manual_withdraw.id,
            'memo': manual_withdraw.memo
        }

        url = settings.BLOCKLINK_BASE_URL + '/api/v1/withdraw/manual/'

        return requests.post(data=data, url=url, headers=self.header, timeout=15)

    def terminate_withdraw(self, transfer_id):
        data = {
            'requester_id': transfer_id,
        }

        url = settings.BLOCKLINK_BASE_URL + '/api/v1/withdraw/terminate/'

        return requests.post(data=data, url=url, headers=self.header, timeout=15)
