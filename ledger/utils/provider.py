import logging
import math
import time
from datetime import datetime
from decimal import Decimal
from json import JSONDecodeError
from math import log10
from typing import List, Union

import requests
from decouple import config
from django.conf import settings
from django.core.cache import cache
from urllib3.exceptions import ReadTimeoutError

from accounts.verifiers.jibit import Response
from ledger.exceptions import HedgeError
from ledger.models import Asset, Transfer
from ledger.utils.cache import get_cache_func_key
from ledger.utils.dto import MarketInfo, NetworkInfo, WithdrawStatus, CoinInfo
from ledger.utils.external_price import SELL, BUY
from ledger.utils.fields import DONE
from ledger.utils.precision import floor_precision
from ledger.utils.price import get_price

TRADE, BORROW, LIQUIDATION, WITHDRAW, HEDGE, PROVIDE_BASE, FAKE = \
    'trade', 'borrow', 'liquid', 'withdraw', 'hedge', 'prv-base', 'fake'

logger = logging.getLogger(__name__)

SPOT, FUTURES = 'spot', 'futures'
BINANCE, KUCOIN, MEXC = 'binance', 'kucoin', 'mexc'


class ProviderRequester:
    def collect_api(self, path: str, method: str = 'GET', data: dict = None, cache_timeout: int = None,
                    timeout: float = 10) -> Response:
        cache_key = None
        if cache_timeout:
            cache_key = 'provider:' + get_cache_func_key(self.__class__, path, method, data)
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return Response(data=cached_result)

        result = self._collect_api(path, method, data, timeout=timeout)

        if cache_timeout and result.success:
            cache.set(cache_key, result.data, cache_timeout)

        return result

    def _collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 10) -> Response:
        if data is None:
            data = {}

        url = config('PROVIDER_BASE_URL', default='https://provider.raastin.com') + path

        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': config('PROVIDER_TOKEN')},
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)
        except (requests.exceptions.ConnectionError, ReadTimeoutError, requests.exceptions.Timeout):
            raise TimeoutError

        try:
            resp_json = resp.json()
        except JSONDecodeError:
            resp_json = None

        return Response(data=resp_json, success=resp.ok, status_code=resp.status_code)

    def get_market_info(self, asset: Asset, side: str) -> MarketInfo:
        data = self.collect_api('/api/v1/market/', data={'coin': asset.symbol, 'side': side}, cache_timeout=300).data
        return MarketInfo(
            id=data['id'],
            coin=asset.symbol,
            base_coin=data['base_coin'],
            type=data['type'],
            exchange=data['exchange'],

            tick_size=data['tick_size'],
            step_size=data['step_size'],
            min_notional=data['min_notional'],
            min_quantity=data['min_quantity'],
            max_quantity=data['max_quantity'],
        )

    def get_spot_balance_map(self, exchange: str, market: str = 'trade') -> dict:
        resp = self.collect_api('/api/v1/spot/balance/', data={'exchange': exchange, 'market': market})
        if not resp.success:
            return {}
        return resp.data

    def get_futures_info(self, exchange: str) -> dict:
        resp = self.collect_api('/api/v1/futures/', timeout=30, data={'exchange': exchange})
        return resp.data

    def get_network_info(self, coin: str, network: str = None) -> List[NetworkInfo]:
        params = {'coin': coin}
        info = []

        if network:
            params['network'] = network

        resp = self.collect_api('/api/v1/networks/', timeout=30, data=params)
        if resp.success:
            for data in resp.data:
                info.append(NetworkInfo(**data))

        return info

    def try_hedge_new_order(self, request_id: str, asset: Asset, scope: str, buy_amount: Decimal = 0,
                            hedge_price: Decimal = None):
        if settings.DEBUG_OR_TESTING_OR_STAGING:
            logger.info('ignored due to debug')
            return

        if not asset.hedge:
            logger.info('ignored due to no hedge method')
            return

        side = BUY if buy_amount > 0 else SELL

        market_info = self.get_market_info(asset, side=side)

        step_size = market_info.step_size

        # Hedge strategy: don't sell assets ASAP and hold them!

        if buy_amount > 0:
            threshold = step_size / 2
        else:
            threshold = step_size * 2

        if abs(buy_amount) < threshold:
            return

        side = BUY

        if buy_amount < 0:
            buy_amount = -buy_amount
            side = SELL

        round_digits = min(-int(log10(step_size)), 8)

        order_amount = round(buy_amount, round_digits)

        price = get_price(
            asset.symbol + Asset.USDT,
            side=BUY
        )
        min_notional = market_info.min_notional * Decimal('1.1')

        if order_amount * price < min_notional:
            logger.info('ignored due to small order')
            return

        if market_info.type == 'spot' and side == SELL:
            balance_map = self.get_balances(market_info.id, market_info.type)['balances']
            balance = Decimal(balance_map.get(asset.symbol, 0))

            if balance < order_amount:
                diff = order_amount - balance

                if diff * price < min_notional:
                    order_amount = floor_precision(balance, round_digits)

                    if order_amount * price < min_notional:
                        logger.info('ignored due to small order')
                        return

        if side == BUY and market_info.base_coin == 'BUSD':
            busd_balance = Decimal(self.get_spot_balance_map(market_info.exchange)['BUSD'])
            needed_busd = order_amount * price

            if needed_busd > busd_balance:
                logger.info('providing busd for order')
                to_buy_busd = max(math.ceil((needed_busd - busd_balance) * Decimal('1.01')), min_notional)

                self.new_order(
                    request_id=request_id,
                    asset=Asset.get('BUSD'),
                    side=BUY,
                    amount=Decimal(to_buy_busd),
                    scope='prv-base',
                )

        if hedge_price:
            hedge_price = floor_precision(hedge_price, min(-int(log10(market_info.tick_size)), 8))

        order = self.new_order(
            request_id=request_id,
            asset=asset,
            side=side,
            amount=order_amount,
            price=hedge_price,
            scope=scope
        )

        if not order:
            raise HedgeError

        return True

    def new_order(self, request_id: str, asset: Asset, scope: str, amount: Decimal, side: str, price: Decimal = None):
        data = {
            'request_id': request_id,
            'coin': asset.symbol,
            'scope': scope,
            'amount': str(amount),
            'side': side,
            'price': price and str(price)
        }

        resp = self.collect_api('/api/v1/orders/', method='POST', data=data, timeout=15)

        if not resp.success:
            logger.info('provider new order failed with status=%s and %s' % (resp.status_code, resp.data))

        return resp.success

    def new_withdraw(self, transfer: Transfer) -> Response:
        assert not transfer.deposit

        resp = self.collect_api('/api/v1/withdraw/', method='POST', data={
            'coin': transfer.asset.symbol,
            'network': transfer.network.symbol,
            'amount': str(transfer.amount),
            'address': transfer.out_address,
            'memo': transfer.memo,
            'requester_id': transfer.id,
        })

        if not resp.success:
            logger.error('Failed to provider withdraw', extra={
                'resp': resp.data
            })

        return resp

    def get_transfer_status(self, transfer: Transfer) -> Union[WithdrawStatus, None]:
        resp = self.collect_api('/api/v1/withdraw/%d/' % transfer.id)
        data = resp.data['status']

        if not data:
            return

        return WithdrawStatus(
            status=data['status'],
            tx_id=data.get('tx_id') or ''
        )

    def get_order(self, request_id: str):
        return self.collect_api('/api/v1/orders/details/', method='GET', data={
            'request_id': request_id,
        }, timeout=30).data

    def get_coins_info(self, coins: List[str] = None) -> List[dict]:
        data = {}
        if coins:
            data['coins'] = ','.join(coins)

        resp = self.collect_api('/api/v1/coins/info/', data=data, timeout=30, cache_timeout=300)

        if not resp.success:
            return []

        return resp.data

    def get_price(self, symbol: str, side: str, delay: int = 300, when: datetime = None) -> Decimal:
        resp = self.collect_api('/api/v1/market/price/history/', data={
            'symbol': symbol,
            'side': side,
            'delay': delay,
            'datetime': when
        })

        if resp.success:
            return Decimal(resp.data['price'])

    def get_avg_trade_price(self, symbol: str, start: datetime, end: datetime) -> Decimal:
        resp = self.collect_api('/api/v1/market/price/trade/avg/', data={
            'symbol': symbol,
            'start': start,
            'end': end
        })

        if resp.success:
            return Decimal(resp.data['price'])

    def get_profiles(self) -> list:
        resp = self.collect_api('/api/v1/profiles/')

        if not resp.success:
            return []

        return resp.data

    def get_balances(self, profile_id: int, market: str) -> Union[dict, None]:
        resp = self.collect_api(
            path='/api/v1/profiles/{}/{}/balances/'.format(profile_id, market),
            timeout=60
        )

        if not resp.success:
            return

        return resp.data

    def get_income_history(self, profile_id: int, start: datetime, end: datetime) -> list:
        resp = self.collect_api('/api/v1/incomes/', data={
            'profile_id': profile_id,
            'start': start,
            'end': end
        })

        return resp.data


class MockProviderRequester(ProviderRequester):
    def _collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 10):
        if config('PROVIDER_TIMEOUT_MODE', default=None):
            time.sleep(60)
            raise requests.exceptions.Timeout

    def get_market_info(self, asset: Asset, side: str) -> MarketInfo:
        self._collect_api('/')

        return MarketInfo(
            id=1,
            coin=asset.symbol,
            base_coin=Asset.USDT,
            exchange='binance',
            type='spot',
            step_size=Decimal(1),
            tick_size=Decimal(1),
            min_quantity=Decimal(1),
            max_quantity=Decimal(1000),
            min_notional=Decimal(10)
        )

    def get_spot_balance_map(self, exchange: str, market: str = 'trade') -> dict:
        self._collect_api('/')
        return {}

    def get_futures_info(self, exchange: str) -> dict:
        self._collect_api('/')
        return {}

    def get_network_info(self, asset: str, network: str = None) -> List[NetworkInfo]:
        self._collect_api('/')

        if not network:
            network = 'TRX'

        return [
            NetworkInfo(
                coin=asset,
                network=network,
                withdraw_min=Decimal(1),
                withdraw_max=Decimal(100),
                withdraw_fee=Decimal(1),
                withdraw_enable=True,
                deposit_enable=True,
                address_regex=r'\w+'
            )
        ]

    def try_hedge_new_order(self, request_id: str, asset: Asset, scope: str, buy_amount: Decimal = 0, hedge_price: Decimal = None):
        self._collect_api('/')

    def new_order(self, request_id: str, asset: Asset, scope: str, amount: Decimal, side: str, price: Decimal = None):
        self._collect_api('/')
        return True

    def new_withdraw(self, transfer: Transfer):
        self._collect_api('/')
        return True

    def get_transfer_status(self, transfer: Transfer) -> WithdrawStatus:
        self._collect_api('/')
        return WithdrawStatus(status=DONE, tx_id='tx')

    def get_coins_info(self, coins: List[str] = None) -> List[dict]:
        self._collect_api('/')
        data = []
        for c in Asset.objects.filter(enable=True):
            data.append(
                CoinInfo(
                    coin=c.symbol,
                    weekly_trend_url='https://s3.coinmarketcap.com/generated/sparklines/web/1d/2781/825.svg?v=463140',
                    volume_24h=5
                ).__dict__
            )

        return data

    def get_price(self, symbol: str, side: str, delay: int = 300, when: datetime = None) -> Decimal:
        self._collect_api('/')
        return Decimal(30000)

    def get_avg_trade_price(self, symbol: str, start: datetime, end: datetime) -> Decimal:
        self._collect_api('/')
        return Decimal(30000)

    def get_order(self, request_id: str):
        self._collect_api('/')
        return {
            'filled_price': Decimal(1),
            'filled_amount': Decimal(1),
        }

    def get_income_history(self, profile_id: int, start: datetime, end: datetime) -> list:
        self._collect_api('/')
        return [
            {
                "symbol": "BTCUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.05900757",
                "asset": "USDT",
                "time": 1678032000000,
                "info": "FUNDING_FEE",
                "tranId": 6847922729675042940,
                "tradeId": ""
            },
        ]


def get_provider_requester() -> ProviderRequester:
    if settings.DEBUG_OR_TESTING_OR_STAGING:
        return MockProviderRequester()
    else:
        return ProviderRequester()
