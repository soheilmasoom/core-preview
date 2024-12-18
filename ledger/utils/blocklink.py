from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple

from decouple import config
from django.conf import settings

from accounts.verifiers.jibit import Response
from ledger.exceptions import FetchError
from ledger.utils.base_requester import BaseRequester

__all__ = ('get_blocklink_requester', )


class BlocklinkRequester(BaseRequester):
    CACHE_PREFIX = 'blocklink'
    BASE_TIMEOUT = 30

    def get_base_url(self):
        return config('BLOCKLINK_BASE_URL', default='https://blocklink.raastinwallet.com')

    def get_auth_token(self):
        return config('BLOCKLINK_TOKEN')

    def create_wallet(self, arch: str, tag: str) -> Response:
        data = {
            'architecture': arch,
            'tag': tag
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

        balances = defaultdict(Decimal)

        for hw in resp.data:
            balances[(hw['coin'], hw['network'])] += Decimal(hw['balance'])

        return dict(balances)

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

    def terminate_withdraw(self, transfer_id, is_manual:bool = False) -> Response:
        data = {
            'requester_id': transfer_id,
            'is_manual': is_manual
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

    def get_contract_info(self, coin: str, network: str) -> Response:
        return self.collect_api(
            path='/api/v1/tracker/contracts/info/',
            data={
                'coin': coin,
                'network': network
            }
        )

    def submit_cold_wallet(self, arch:str, address:str):
        data = {
            'architecture': arch,
            'address': address
        }

        status_code = self.collect_api(
            path='/api/v1/tracker/cold-wallets/submit/',
            method='POST',
            data=data
        ).status_code

        return status_code and status_code in [200, 201]

    def get_cold_wallets(self):
        return self.collect_api(
            path='/api/v1/tracker/cold-wallets/',
            method='GET',
        )


class MockBlocklinkRequester(BlocklinkRequester):
    def collect_api(self, path: str, method: str = 'GET', data: dict = None, cache_timeout: int = None, timeout: float = ...) -> Response:
        pass

    def get_network_arch(self, network: str) -> str:
        if network == 'XRP':
            return 'XRP'
        else:
            return 'ETH'


_requester = BlocklinkRequester()  # to maintain tcp session


def get_blocklink_requester() -> BlocklinkRequester:
    if settings.DEBUG_OR_TESTING:
        return MockBlocklinkRequester()
    else:
        return _requester
