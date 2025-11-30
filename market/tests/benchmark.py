import random
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Thread
from time import time

from django.test import Client
from django.test import TestCase
from django.utils import timezone

from accounts.models import SystemConfig, Account
from ledger.models import Asset, Wallet
from ledger.utils.external_price import SELL, BUY
from ledger.utils.test import new_account, set_price
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol
from market.utils.order_utils import new_order

USDT_IRT_PRICE = 20000
BTC_USDT_PRICE = Decimal('1000')

TO_TRANSFER_USDT = 100


class OrderBenchmarkTestCase(TestCase):

    def setUp(self) -> None:
        sys = SystemConfig.get_system_config()
        sys.active = True
        sys.max_margin_leverage = 8
        sys.save()

        self.insurance_account = new_account()

        self.account = new_account()
        self.user = self.account.user
        self.user.show_margin = True
        self.user.margin_quiz_pass_date = timezone.now()
        self.user.save()

        self.account2 = new_account()
        self.user2 = self.account2.user
        self.user2.show_margin = True
        self.user2.margin_quiz_pass_date = timezone.now()
        self.user2.save()

        self.account3 = new_account()
        self.user3 = self.account2.user
        self.user3.show_margin = True
        self.user3.margin_quiz_pass_date = timezone.now()
        self.user3.save()

        self.usdt = Asset.get(Asset.USDT)

        self.btc = Asset.get('BTC')

        self.usdt.get_wallet(self.account).airdrop(BTC_USDT_PRICE * TO_TRANSFER_USDT * 10000)

        self.usdt.get_wallet(self.account2).airdrop(TO_TRANSFER_USDT * 30 * BTC_USDT_PRICE)
        self.btc.get_wallet(self.account2).airdrop(TO_TRANSFER_USDT * 30)

        self.usdt.get_wallet(self.account3).airdrop(TO_TRANSFER_USDT * 30 * BTC_USDT_PRICE)
        self.btc.get_wallet(self.account3).airdrop(TO_TRANSFER_USDT * 30)

        self.client = Client()
        self.client.force_login(self.user)

        set_price(self.usdt, USDT_IRT_PRICE)
        set_price(self.btc, int(BTC_USDT_PRICE))

        self.btcusdt = PairSymbol.objects.get(name='BTCUSDT')
        self.btcusdt.enable = True
        self.btcusdt.margin_enable = True
        self.btcusdt.last_trade_price = BTC_USDT_PRICE
        self.btcusdt.save()

        self.btc.enable = True
        self.btc.save()
        self.usdt.enable = True
        self.usdt.save()
        for i in range(0, 100):
            new_account()

    def place_order(self, amount, price, side, symbol='BTCUSDT', market='spot', fill_type='limit', is_open_position=False):
        resp = self.client.post('/api/v1/market/orders/', {
            'symbol': symbol,
            'side': side,
            'price': price,
            'amount': amount,
            'fill_type': fill_type,
            'market': market,
            'is_open_position': is_open_position
        })
        print(resp.json())

    def test_100_buy(self):
        start_time = time()
        num = 400
        n = 4 * num
        side = SELL

        with WalletPipeline() as pipeline:
            kwargs = {
                    'pipeline': pipeline,
                    'symbol': self.btcusdt,
                    'account': self.account2,
                    'side': side,
                    'amount': Decimal(TO_TRANSFER_USDT * 30 / n),
                    'market': Wallet.SPOT,
                    'price': BTC_USDT_PRICE
                }
            with ThreadPoolExecutor(max_workers=3) as pool:
                print('start')
                futures = [pool.submit(new_order, **kwargs) for i in range(0, 10)]

                for f in futures:
                    f.result()

        print(f"{num * 4} maker order End time: {time() - start_time}")

        # with WalletPipeline() as pipeline:
        #     for i in range(0, num):
        #
        #         new_order(
        #             pipeline,
        #             self.btcusdt,
        #             self.account2,
        #             side=SELL,
        #             amount=Decimal(TO_TRANSFER_USDT * 30 / num),
        #             market=Wallet.SPOT,
        #             price=BTC_USDT_PRICE
        #         )
        #         new_order(
        #             pipeline,
        #             self.btcusdt,
        #             self.account2,
        #             side=BUY,
        #             amount=Decimal(TO_TRANSFER_USDT * 30 / num),
        #             market=Wallet.SPOT,
        #             price=BTC_USDT_PRICE / 2
        #         )
        #
        #         new_order(
        #             pipeline,
        #             self.btcusdt,
        #             self.account3,
        #             side=SELL,
        #             amount=Decimal(TO_TRANSFER_USDT * 30 / num),
        #             market=Wallet.SPOT,
        #             price=BTC_USDT_PRICE
        #         )
        #         new_order(
        #             pipeline,
        #             self.btcusdt,
        #             self.account3,
        #             side=BUY,
        #             amount=Decimal(TO_TRANSFER_USDT * 30 / num),
        #             market=Wallet.SPOT,
        #             price=BTC_USDT_PRICE / 2
        #         )

        # print(f"{num * 4} maker order End time: {time() - start_time}")

        # return
        # def place_order():
        #     buy_amount = Decimal(TO_TRANSFER_USDT * 30 / 100)
        #     for i in range(0, 100):
        #         self.place_order(amount=buy_amount, side=BUY, price=BTC_USDT_PRICE, fill_type='market')
        #
        # print('Start Benchmarking Orders')
        # start_time = time()
        # place_order()
        # print(f"End time: {time() - start_time}")

    def benchmark(self, n=None, worker=32):
        num = 400
        n = n or 4 * num
        btcusdt = PairSymbol.objects.get(name='BTCUSDT')
        account = Account.objects.all().last()

        usdt = Asset.get(Asset.USDT)
        usdt.get_wallet(account).airdrop(BTC_USDT_PRICE * TO_TRANSFER_USDT * 10000000000)

        btc = Asset.get('BTC')
        btc.get_wallet(account).airdrop(BTC_USDT_PRICE * TO_TRANSFER_USDT * 10000000000)

        start_time = time()
        with WalletPipeline() as pipeline:
            kwargs = {
                'pipeline': pipeline,
                'symbol': btcusdt,
                'account': account,
                'side': SELL,
                'amount': Decimal(TO_TRANSFER_USDT * 30 / n),
                'market': Wallet.SPOT,
                'price': BTC_USDT_PRICE
            }
            with ThreadPoolExecutor(max_workers=worker) as pool:
                futures = [pool.submit(new_order, **kwargs) for i in range(0, n)]

                for f in futures:
                    f.result()
        spent_time = time() - start_time
        print(f"{n} maker order End time: {spent_time}, oder per second: {n / spent_time}")
