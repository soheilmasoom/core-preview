from decimal import Decimal
from uuid import uuid4

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import Account
from ledger.models import Asset, Trx, Wallet, MarginPosition
from ledger.utils.external_price import SELL, BUY
from ledger.utils.test import new_account, set_price
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol, Trade, Order
from market.models.pair_symbol import DEFAULT_TAKER_FEE, DEFAULT_MAKER_FEE
from market.utils.order_utils import new_order


# todo: check referral for USDTIRT
from market.utils.order import get_filled_price


class CreateOrderTestCase(TestCase):
    def setUp(self):
        PairSymbol.objects.filter(name='BTCIRT').update(enable=True)
        PairSymbol.objects.filter(name='BTCUSDT').update(enable=True)
        Asset.objects.filter(symbol='BTC').update(enable=True)

        self.account = new_account()

        self.account_2 = new_account()
        self.client = Client()

        self.irt = Asset.get(Asset.IRT)
        self.usdt = Asset.get(Asset.USDT)
        self.btc = Asset.get('BTC')
        set_price(self.usdt, 30000)
        set_price(self.btc, 30000)

        self.btcirt = PairSymbol.objects.get(name='BTCIRT')
        self.btcusdt = PairSymbol.objects.get(name='BTCUSDT')

        # Asset.objects.filter(symbol='BTC').update(margin_enable=True)
        # Asset.objects.filter(symbol='USDT').update(enable=True, margin_enable=True)

        self.fill = Trade.objects.all()

        with WalletPipeline() as pipeline:

            for market in (Wallet.SPOT, Wallet.MARGIN):
                pipeline.new_trx(
                    group_id=uuid4(),
                    sender=self.usdt.get_wallet(Account.system()),
                    receiver=self.usdt.get_wallet(self.account, market=market),
                    amount=1000 * 1000 * 10000,
                    scope=Trx.TRANSFER
                )
                pipeline.new_trx(
                    group_id=uuid4(),
                    sender=self.irt.get_wallet(Account.system()),
                    receiver=self.irt.get_wallet(self.account, market=market),
                    amount=1000 * 1000 * 10000,
                    scope=Trx.TRANSFER
                )
                pipeline.new_trx(
                    group_id=uuid4(),
                    sender=self.btc.get_wallet(Account.system()),
                    receiver=self.btc.get_wallet(self.account, market=market),
                    amount=1000 * 1000 * 10000,
                    scope=Trx.TRANSFER
                )

        self.account.user.margin_quiz_pass_date = timezone.now()
        self.account.user.show_margin = True
        self.account.user.save()

        self.account_2.user.margin_quiz_pass_date = timezone.now()
        self.account_2.user.show_margin = True
        self.account_2.user.save()

    def test_create_order(self):

        self.client.force_login(self.account.user)
        # wallets = self.irt.get_wallet(self.account)
        resp = self.client.post('/api/v1/market/orders/', {
            'symbol': 'BTCIRT',
            'amount': '1.5',
            'price': '200000',
            'side': 'buy',
            'fill_type': 'limit',
        })
        self.assertEqual(resp.status_code, 201)

    def test_fill_order(self):
        with WalletPipeline() as pipeline:
            order = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, 200000)
            order_2 = new_order(pipeline, self.btcirt, Account.system(), BUY, 2, 200000)
        order.refresh_from_db()

        trade_pair = Trade.objects.order_by('-id')[:2]

        self.assertEqual(order.status, Order.FILLED)
        self.assertEqual(trade_pair[0].price, 200000)
        self.assertEqual(trade_pair[0].amount, 2)
        self.assertEqual(trade_pair[1].price, 200000)
        self.assertEqual(trade_pair[1].amount, 2)

    def test_fill_order_with_different_price(self):
        with WalletPipeline() as pipeline:
            order_3 = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, 200000)
            order_4 = new_order(pipeline, self.btcirt, self.account, BUY, 2, 200010)
        order_3.refresh_from_db(), order_4.refresh_from_db()

        fill_order = Trade.objects.get(order_id=order_3.id)

        trx_asset = Trx.objects.get(
            group_id=fill_order.group_id,
            scope=Trx.TRADE,
            sender=self.btc.get_wallet(Account.system())
        )
        trx_base_asset = Trx.objects.get(
            group_id=fill_order.group_id,
            scope=Trx.TRADE,
            sender=self.irt.get_wallet(self.account)
        )
        trx_taker_fee = Trx.objects.get(
            group_id=fill_order.group_id,
            scope=Trx.COMMISSION,
            sender=self.btc.get_wallet(self.account)
        )
        if DEFAULT_MAKER_FEE != Decimal(0):
            trx_maker_fee = Trx.objects.get(
                group_id=fill_order.group_id,
                scope=Trx.COMMISSION,
                sender=self.btc.get_wallet(Account.system())
            )
            self.assertEqual(trx_maker_fee, 2 * DEFAULT_MAKER_FEE)

        self.assertEqual(trx_asset.amount, 2)
        self.assertEqual(trx_base_asset.amount, 400000)
        self.assertEqual(trx_taker_fee.amount, 2 * DEFAULT_TAKER_FEE)

        self.assertEqual(order_3.status, Order.FILLED)
        self.assertEqual(order_4.status, Order.FILLED)

        self.assertEqual(order_3.filled_amount, 2)
        self.assertEqual(order_4.filled_amount, 2)

        self.assertEqual(get_filled_price(order_3), 200000)
        self.assertEqual(get_filled_price(order_4), 200000)

        self.assertEqual(fill_order.price, 200000)
        self.assertEqual(fill_order.amount, 2)

    def test_fill_three_order(self):
        account = new_account()
        self.irt.get_wallet(account).airdrop(6 * 200020)
        with WalletPipeline() as pipeline:
            order_5 = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, 200000)
            order_6 = new_order(pipeline, self.btcirt, Account.system(), SELL, 3, 200010)
            order_7 = new_order(pipeline, self.btcirt, account, BUY, 6, 200020)

        order_5.refresh_from_db(), order_6.refresh_from_db(), order_7.refresh_from_db()

        trade_between_5_7 = Trade.objects.get(order_id=order_5.id)
        trade_between_7_5 = Trade.objects.get(order_id=order_7.id, group_id=trade_between_5_7.group_id)
        trade_between_6_7 = Trade.objects.get(order_id=order_6.id)
        trade_between_7_6 = Trade.objects.get(order_id=order_7.id, group_id=trade_between_6_7.group_id)

        self.assertEqual(trade_between_7_5.fee_amount, 2 * DEFAULT_TAKER_FEE)
        self.assertEqual(trade_between_5_7.fee_amount, 2 * DEFAULT_MAKER_FEE)
        self.assertEqual(trade_between_7_6.fee_amount, 3 * DEFAULT_TAKER_FEE)
        self.assertEqual(trade_between_6_7.fee_amount, 3 * DEFAULT_MAKER_FEE)

        self.assertEqual(order_5.filled_amount, 2)
        self.assertEqual(order_6.filled_amount, 3)
        self.assertEqual(order_7.filled_amount, 5)

        self.assertEqual(get_filled_price(order_5), 200000)
        self.assertEqual(get_filled_price(order_6), 200010)

        self.assertEqual(order_5.status, Order.FILLED)
        self.assertEqual(order_6.status, Order.FILLED)
        self.assertEqual(order_7.status, Order.NEW)

        self.assertEqual(trade_between_5_7.amount, 2)
        self.assertEqual(trade_between_6_7.amount, 3)
        self.assertEqual(trade_between_7_5.amount, 2)
        self.assertEqual(trade_between_7_6.amount, 3)

        self.assertEqual(trade_between_5_7.price, 200000)
        self.assertEqual(trade_between_6_7.price, 200010)
        self.assertEqual(trade_between_7_5.price, 200000)
        self.assertEqual(trade_between_7_6.price, 200010)

    def test_not_fill_order(self):
        with WalletPipeline() as pipeline:
            order_8 = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, 200000)
            order_9 = new_order(pipeline, self.btcirt, Account.system(), BUY, 2, 150000)

        order_8.refresh_from_db(), order_9.refresh_from_db()

        self.assertEqual(order_8.filled_amount, 0)
        self.assertEqual(order_9.filled_amount, 0)
        self.assertEqual(order_8.status, Order.NEW)
        self.assertEqual(order_9.status, Order.NEW)

    def test_cancel_order_after_partial_filled(self):
        with WalletPipeline() as pipeline:
            order_10 = new_order(pipeline, self.btcirt, Account.system(), SELL, 20, 200000)
            order_11 = new_order(pipeline, self.btcirt, Account.system(), BUY, 10, 200005)

        order_10.cancel()

        order_10.refresh_from_db(), order_11.refresh_from_db()

        fill_order = Trade.objects.get(order_id=order_10.id)

        self.assertEqual(order_10.status, Order.CANCELED)
        self.assertEqual(order_11.status, Order.FILLED)

        self.assertEqual(order_10.filled_amount, 10)
        self.assertEqual(order_11.filled_amount, 10)

        self.assertEqual(fill_order.price, 200000)
        self.assertEqual(fill_order.amount, 10)

    def test_cancel_order_after_complete_filled(self):
        with WalletPipeline() as pipeline:
            order_12 = new_order(pipeline, self.btcirt, Account.system(), SELL, 20, 200000)
            order_13 = new_order(pipeline, self.btcirt, Account.system(), BUY, 20, 200005)

        order_12.cancel()

        order_12.refresh_from_db(), order_13.refresh_from_db()

        fill_order = Trade.objects.get(order_id=order_12.id)

        self.assertEqual(order_12.status, Order.FILLED)
        self.assertEqual(order_13.status, Order.FILLED)

        self.assertEqual(order_12.filled_amount, 20)
        self.assertEqual(order_13.filled_amount, 20)

        self.assertEqual(fill_order.price, 200000)
        self.assertEqual(fill_order.amount, 20)

    def test_cancel_before_fill(self):
        with WalletPipeline() as pipeline:
            order_14 = new_order(pipeline, self.btcirt, Account.system(), SELL, 20, 200000)
            order_14.cancel()
            order_15 = new_order(pipeline, self.btcirt, Account.system(), BUY, 20, 200000)

        order_14.refresh_from_db(), order_15.refresh_from_db()

        self.assertEqual(order_14.status, Order.CANCELED)
        self.assertEqual(order_15.status, Order.NEW)

        self.assertEqual(order_14.filled_amount, 0)
        self.assertEqual(order_15.filled_amount, 0)

    def test_not_enough_for_sell(self):
        self.client.force_login(self.account_2.user)
        # wallet = self.btc.get_wallet(self.account_2)
        resp = self.client.post('/api/v1/market/orders/', {
            'symbol': 'BTCIRT',
            'amount': '10',
            'price': '300000',
            'side': 'sell',
            'fill_type': 'limit',
        })
        self.assertEqual(resp.status_code, 400)

    def test_market_sell_order(self):
        with WalletPipeline() as pipeline:
            limit_order = new_order(pipeline, self.btcirt, Account.system(), BUY, 2, 2000000)
            order = new_order(pipeline, self.btcirt, Account.system(), SELL, Decimal('0.1'), fill_type=Order.MARKET)
        order.refresh_from_db()

        trade_pair = Trade.objects.order_by('-id')[:2]

        self.assertEqual(order.status, Order.FILLED)
        self.assertEqual(trade_pair[0].price, 2000000)
        self.assertEqual(trade_pair[0].amount, Decimal('0.1'))
        self.assertEqual(trade_pair[1].price, 2000000)
        self.assertEqual(trade_pair[1].amount, Decimal('0.1'))

    def test_market_order_large_amount(self):
        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcirt, Account.system(), BUY, 1, 2000000)
            order = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, fill_type=Order.MARKET)
        order.refresh_from_db()

        trade_pair = Trade.objects.order_by('-id')[:2]

        self.assertEqual(order.status, Order.CANCELED)
        self.assertEqual(trade_pair[0].price, 2000000)
        self.assertEqual(trade_pair[0].amount, 1)
        self.assertEqual(trade_pair[1].price, 2000000)
        self.assertEqual(trade_pair[1].amount, 1)

    def test_market_order_multi_match_price(self):
        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcirt, Account.system(), BUY, Decimal('0.5'), 2000000)
            new_order(pipeline, self.btcirt, Account.system(), BUY, Decimal('0.5'), 1980000)
            order = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, fill_type=Order.MARKET)
        order.refresh_from_db()

        self.assertEqual(order.status, Order.CANCELED)

        fill_orders = Trade.objects.filter(order_id=order.id).order_by('-id')[:2]
        for fill_order in fill_orders:
            maker_trade = Trade.objects.filter(group_id=fill_order.group_id).exclude(id=fill_order.id).first()
            order = Order.objects.get(id=maker_trade.order_id)
            self.assertEqual(fill_order.price, order.price)
            self.assertEqual(fill_order.amount, Decimal('0.5'))

    def test_market_order_multi_match_price_unmatched_orders(self):
        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcirt, Account.system(), BUY, Decimal('0.5'), 2000000)
            new_order(pipeline, self.btcirt, Account.system(), BUY, Decimal('0.5'), 1980000)
            new_order(pipeline, self.btcirt, Account.system(), BUY, Decimal('0.5'), 1900000)
            order = new_order(pipeline, self.btcirt, Account.system(), SELL, 2, fill_type=Order.MARKET)
        order.refresh_from_db()

        self.assertEqual(order.status, Order.CANCELED)
        self.assertEqual(order.filled_amount, 1)

        assert Trade.objects.filter(order_id=order.id).count() == 2
        fill_orders = Trade.objects.filter(order_id=order.id).order_by('-id')[:2]
        for fill_order in fill_orders:
            maker_trade = Trade.objects.filter(group_id=fill_order.group_id).exclude(id=fill_order.id).first()
            self.assertEqual(fill_order.price, maker_trade.price)
            self.assertEqual(fill_order.amount, Decimal('0.5'))
