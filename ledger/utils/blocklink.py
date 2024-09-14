from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple

from decouple import config
from django.conf import settings

from ledger.exceptions import FetchError
from accounts.models import Account
from accounts.verifiers.jibit import Response
from ledger.utils.base_requester import BaseRequester

__all__ = ('get_blocklink_requester', )


class BlocklinkRequester(BaseRequester):
    CACHE_PREFIX = 'blocklink'
    BASE_TIMEOUT = 30

    def get_base_url(self):
        return config('BLOCKLINK_BASE_URL', default='https://blocklink.raastinwallet.com')

    def get_auth_token(self):
        return config('BLOCKLINK_TOKEN')

    def create_wallet(self, account: Account, arch: str) -> Response:
        data = {
            'architecture': arch,
            'tag': '{brand}-base-{account_id}'.format(
                brand=settings.BRAND_EN.lower(),
                account_id=account.id,
            )
        }

        return self.collect_api(
            path='/api/v1/tracker/wallets/',
            method='POST',
            data=data
        )

    def refresh_deposits(self, address: str, arch: str):
        assert arch == 'SOL'

        data = {
            'architecture': arch,
            'pointer_address': address
        }
        return self.collect_api(
            path='/api/v1/tracker/address/update/',
            method='PUT',
            data=data
        )

    def get_network_arch(self, network: str) -> str:
        resp = self.collect_api(
            path='/api/v1/tracker/architecture/',
            data={
                'network': network,
            },
            cache_timeout=3600
        )

        return resp.data.get('architecture')

    def get_assets(self) -> Dict[str, Dict[str, Dict]]:
        resp = self.collect_api(
            path='/api/v1/hotwallet/amount/',
            data={'network': 1},
            cache_timeout=60
        )

        if not resp.ok:
            raise FetchError

        result = defaultdict(dict)

        for asset in resp.data:
            result[asset['network']][asset['coin']] = {
                'amount': Decimal(asset['amount']),
                'free': Decimal(asset['free']),
            }

        return result

    def get_hotwallet_balances(self) -> Dict[Tuple[str, str], Decimal]:
        resp = self.collect_api(
            path='/api/v1/hotwallet/balances/',
            cache_timeout=60
        )

        if not resp.ok:
            raise FetchError

        return {
            (hw['coin'], hw['network']): Decimal(hw['balance']) for hw in resp.data
        }

    def withdraw(self, receiver_address: str, amount: Decimal, network: str, coin: str, transfer_id: int,
                 memo: str = None, manual: bool = False) -> Response:

        data = {
            'receiver_address': receiver_address,
            'amount': str(amount),
            'network': network,
            'coin': coin,
            'requester_id': transfer_id,
        }

        if memo:
            data['memo'] = memo

        if manual:
            path = '/api/v1/withdraw/manual/'
        else:
            path = '/api/v1/withdraw/'

        return self.collect_api(
            path=path,
            method='POST',
            data=data
        )

    def terminate_withdraw(self, transfer_id) -> Response:
        data = {
            'requester_id': transfer_id,
        }

        return self.collect_api(
            path='/api/v1/withdraw/terminate/',
            method='POST',
            data=data
        )

    def get_income(self, start: datetime, end: datetime):
        return self.collect_api(
            path='/api/v1/tracker/revenue/',
            data={
                'start': start,
                'end': end
            }
        )


class MockBlocklinkRequester(BlocklinkRequester):
    def get_network_arch(self, network: str) -> str:
        if network == 'XRP':
            return 'XRP'
        else:
            return 'ETH'


def get_blocklink_requester() -> BlocklinkRequester:
    if settings.DEBUG_OR_TESTING:
        return MockBlocklinkRequester()
    else:
        return BlocklinkRequester()
