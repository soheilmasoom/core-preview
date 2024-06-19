from decimal import Decimal

from django.db.models import Sum, Q
from django.test import Client
from django.test import TestCase
from django.utils import timezone

from accounts.models import SystemConfig
from ledger.models import Asset, Wallet, MarginPosition
from ledger.utils.external_price import SELL, BUY, SHORT, LONG
from ledger.utils.precision import floor_precision
from ledger.utils.test import new_account, set_price
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol, Order
from market.utils.order_utils import new_order

USDT_IRT_PRICE = 20000
BTC_USDT_PRICE = Decimal('1000')

TO_TRANSFER_USDT = 100


class LeveragedIsolatedMarginTestCase(TestCase):

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
        self.user3 = self.account3.user
        self.user3.show_margin = True
        self.user3.margin_quiz_pass_date = timezone.now()
        self.user3.save()

        self.account_m = new_account()
        self.user_m = self.account_m.user
        self.user_m.show_margin = True
        self.user_m.margin_quiz_pass_date = timezone.now()
        self.user_m.save()

        self.usdt = Asset.get(Asset.USDT)

        self.btc = Asset.get('BTC')

        self.usdt.get_wallet(self.account).airdrop(TO_TRANSFER_USDT * 3)

        self.usdt.get_wallet(self.account2).airdrop(TO_TRANSFER_USDT * 30)
        self.btc.get_wallet(self.account2).airdrop(TO_TRANSFER_USDT * 30)

        self.usdt.get_wallet(self.account_m).airdrop(TO_TRANSFER_USDT * 30)
        self.btc.get_wallet(self.account_m).airdrop(TO_TRANSFER_USDT * 30)

        self.usdt.get_wallet(self.account3).airdrop(TO_TRANSFER_USDT * 30)
        self.btc.get_wallet(self.account3).airdrop(TO_TRANSFER_USDT * 30)

        self.client = Client()
        self.client.force_login(self.user)

        self.client_m = Client()
        self.client_m.force_login(self.user_m)

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

    def transfer_usdt_api(self, amount, type: str = 'sm', check_status=201, client=None):
        resp = (client or self.client).post('/api/v1/margin/transfer/', {
            'amount': amount,
            'type': type,
            'coin': 'USDT',
            'symbol': 'BTCUSDT'
        })
        print(resp.json())
        self.assertEqual(resp.status_code, check_status)

    def get_position_api(self, check_status=200):
        resp = self.client.get('/api/v2/margin/positions/', {
            'symbol': 'BTCUSDT'
        })
        print(resp.json())
        self.assertEqual(resp.status_code, check_status)

    def transfer_btc_api(self, amount, type: str = 'sm', check_status=201):
        resp = self.client.post('/api/v1/margin/transfer/', {
            'amount': amount,
            'type': type,
            'coin': 'BTC',
            'symbol': 'BTCUSDT'
        })
        self.assertEqual(resp.status_code, check_status)

    def print_wallets(self, account=None):
        wallets = Wallet.objects.all()

        print('///////////////////////WALLETS///////////////////////')
        if account:
            wallets = wallets.filter(account=account)

        for w in wallets:
            print('%s %s %s %s: %s' % (w.account, w.asset.symbol, w.market, w.variant, w.get_free()))

        print("/////////////////////////////////////////////////////")

    def place_order(self, amount, price, side, symbol='BTCUSDT', market='spot', fill_type='limit',
                    is_open_position=False, check_status=201, client=None):
        print('place order')
        resp = (client or self.client).post('/api/v1/market/orders/', {
            'symbol': symbol,
            'side': side,
            'price': price,
            'amount': amount,
            'fill_type': fill_type,
            'market': market,
            'is_open_position': is_open_position
        })
        print(resp.json())
        self.assertEqual(resp.status_code, check_status)
        return resp.json()

    def set_leverage(self, leverage: Decimal, check_status=200):
        resp = self.client.post('/api/v2/margin/leverage/', data={
            'leverage': leverage,
        })
        print(resp.json())
        self.assertEqual(resp.status_code, check_status)

    def assert_liquidation(self, account, symbol, liquidate=True):
        mp = MarginPosition.objects.filter(account=account, symbol=symbol).first()

        negetive_wallets = Wallet.objects.filter(
            ~Q(balance=Decimal(0)),
            account=account,
            market=Wallet.MARGIN,
            variant__isnull=False,
        ).count()

        assertion = self.assertEqual if liquidate else self.assertNotEqual
        assertion(negetive_wallets, Decimal('0'))
        assertion(mp.status, MarginPosition.CLOSED)

    def close_position(self, id, check_status=200, client=None):
        print('close position')
        resp = (client or self.client).post('/api/v2/margin/close/', {
            'id': id,
        })
        print(resp.json())
        self.assertEqual(resp.status_code, check_status)

    def test_short_sell_3x(self):
        self.transfer_usdt_api(TO_TRANSFER_USDT / 2)
        loan_amount = TO_TRANSFER_USDT / BTC_USDT_PRICE / 2
        self.set_leverage(Decimal('3'))

        self.print_wallets(self.account)
        self.place_order(amount=3 * loan_amount + Decimal('0.00001'), side=SELL, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True, check_status=400)
        self.place_order(amount=3 * loan_amount, side=SELL, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True)

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=3 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)

        mp = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()
        self.assertEqual(mp.debt_amount, loan_amount * 3)
        self.assertEqual(mp.side, SHORT)
        self.assertTrue(mp.liquidation_price > Decimal('1212'))

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=4 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE - 2)
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=4 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE + 2)
            mp.liquidate(pipeline, False)

        self.print_wallets(self.account)

        mp = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()
        print('mp', mp.debt_amount, mp.total_balance, mp.liquidation_price, mp.side)

    def test_short_sell_5x(self):
        self.transfer_usdt_api(TO_TRANSFER_USDT / 2)
        loan_amount = TO_TRANSFER_USDT / BTC_USDT_PRICE / 2
        leverage = Decimal('5')
        self.set_leverage(leverage)

        self.print_wallets(self.account)
        self.place_order(amount=leverage * loan_amount, side=SELL, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True)

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=leverage * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=10 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=10 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE - 1)

        self.place_order(amount=2 * loan_amount, side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=False)

        self.print_wallets(self.account)

        mp = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()
        print('mp', mp.debt_amount, mp.total_balance, mp.liquidation_price, mp.side, mp.status)

        self.assert_liquidation(self.account, self.btcusdt, False)

    def test_long_buy_3x(self):
        self.transfer_usdt_api(TO_TRANSFER_USDT / 2)
        loan_amount = TO_TRANSFER_USDT / BTC_USDT_PRICE / 2
        self.set_leverage(Decimal('3'))

        self.print_wallets(self.account)
        self.place_order(amount=3 * loan_amount + Decimal('0.00001'), side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True, check_status=400)
        self.place_order(amount=3 * loan_amount, side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True)

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=3 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)

        self.print_wallets(self.account)

        mp = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()
        print('mp', mp.debt_amount, mp.total_balance, mp.liquidation_price, mp.side)
        self.assertEqual(mp.debt_amount, loan_amount * 2 * BTC_USDT_PRICE)
        self.assertEqual(mp.side, LONG)
        self.assertTrue(mp.liquidation_price > Decimal('733'))

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=4 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE - 2)
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=4 * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE + 2)
            mp.liquidate(pipeline, False)

    def test_long_buy_8x(self):
        self.transfer_usdt_api(TO_TRANSFER_USDT / 2)
        loan_amount = TO_TRANSFER_USDT / BTC_USDT_PRICE / 2
        leverage = Decimal('8')
        self.set_leverage(leverage)

        self.print_wallets(self.account)
        self.place_order(amount=leverage * loan_amount, side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True)

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=leverage * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=leverage * loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE - 1)

        self.print_wallets(self.account)

        mp = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()
        print('mp', mp.debt_amount, mp.total_balance, mp.liquidation_price, mp.side)
        self.assertEqual(mp.debt_amount, loan_amount * (leverage - 1) * BTC_USDT_PRICE)
        self.assertEqual(mp.side, LONG)

    def test_long_liquidate_short_close(self):
        self.transfer_usdt_api(TO_TRANSFER_USDT)
        self.transfer_usdt_api(TO_TRANSFER_USDT, client=self.client_m)

        loan_amount = TO_TRANSFER_USDT / BTC_USDT_PRICE
        self.print_wallets(self.account)

        self.place_order(amount=loan_amount, side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True)  # long
        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)

        self.place_order(amount=loan_amount, side=SELL, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True, client=self.client_m)  # Short
        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=BUY, amount=loan_amount, market=Wallet.SPOT, price=BTC_USDT_PRICE)

        long_position = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()

        lp_liquidation_price = floor_precision(long_position.liquidation_price, 2)
        print(';;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;')
        self.print_wallets(self.account)
        self.place_order(amount=loan_amount, side=BUY, market=Wallet.MARGIN, price=lp_liquidation_price - 1, client=self.client_m)
        print(';;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;')

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, self.account2, side=SELL, amount=loan_amount, market=Wallet.SPOT, price=lp_liquidation_price)
            new_order(pipeline, self.btcusdt, self.account3, side=BUY, amount=loan_amount, market=Wallet.SPOT, price=lp_liquidation_price)

        self.assert_liquidation(account=self.account, symbol=self.btcusdt, liquidate=True)
        self.assert_liquidation(account=self.account_m, symbol=self.btcusdt, liquidate=True)

    def test_long_open_short_open(self):
        self.transfer_usdt_api(TO_TRANSFER_USDT)
        self.transfer_usdt_api(TO_TRANSFER_USDT, client=self.client_m)

        loan_amount = TO_TRANSFER_USDT / BTC_USDT_PRICE
        self.print_wallets(self.account)

        self.place_order(amount=loan_amount, side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True)  # long

        self.place_order(amount=loan_amount, side=SELL, market=Wallet.MARGIN, price=BTC_USDT_PRICE, is_open_position=True, client=self.client_m)  # Short

        mp = MarginPosition.objects.filter(account=self.account, symbol=self.btcusdt).first()
        self.assertEqual(mp.status, MarginPosition.OPEN)
        self.assertEqual(mp.side, LONG)

        mp_m = MarginPosition.objects.filter(account=self.account_m, symbol=self.btcusdt).first()
        self.assertEqual(mp_m.status, MarginPosition.OPEN)
        self.assertEqual(mp_m.side, SHORT)

        self.print_wallets(self.account_m)

        self.place_order(amount=loan_amount, side=SELL, market=Wallet.MARGIN, price=BTC_USDT_PRICE)  # long

        self.place_order(amount=loan_amount, side=BUY, market=Wallet.MARGIN, price=BTC_USDT_PRICE, client=self.client_m)  # Short

        self.print_wallets(self.account)
        self.print_wallets(self.account_m)

        self.assert_liquidation(self.account, symbol=self.btcusdt)
