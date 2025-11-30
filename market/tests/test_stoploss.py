from decimal import Decimal
from uuid import uuid4

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import Account
from ledger.models import Asset, Trx, Wallet
from ledger.utils.external_price import SELL, BUY
from ledger.utils.test import new_account, set_price
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol, Trade, Order, StopLoss
from market.utils.order_utils import new_order


USDT_IRT_PRICE = 50000
BTC_USDT_PRICE = 10000


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
        set_price(self.usdt, USDT_IRT_PRICE)
        set_price(self.btc, BTC_USDT_PRICE)

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

        self.client.force_login(self.account.user)

    def create_stop_loss_order(self, symbol, amount, trigger_price, side, fill_type='market'):
        resp = self.client.post('/api/v1/market/stop-loss-orders/', {
            'symbol': symbol,
            'amount': amount,
            'trigger_price': trigger_price,
            'side': side,
            'fill_type': fill_type
        })
        self.assertEqual(resp.status_code, 201)

    def test_stop_loss_sell(self):
        amount = Decimal('2')
        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, Account.system(), SELL, 3 * amount, Decimal(BTC_USDT_PRICE + 1))
            new_order(pipeline, self.btcusdt, Account.system(), BUY, 3 * amount, Decimal(BTC_USDT_PRICE - 100))

        self.create_stop_loss_order(symbol=self.btcusdt, side='sell', trigger_price=Decimal(BTC_USDT_PRICE - 100),
                                    amount=Decimal("1"))

        with WalletPipeline() as pipeline:
            new_order(pipeline, self.btcusdt, Account.system(), SELL, amount, Decimal(BTC_USDT_PRICE - 100))

        stop_loss = StopLoss.objects.all().last()
        self.assertEqual(stop_loss.amount, stop_loss.filled_amount)
