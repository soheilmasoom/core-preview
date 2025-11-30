from decimal import Decimal
from uuid import uuid4

from django.db.models import Sum
from django.test import TestCase

from accounts.models import Account
from ledger.exceptions import InsufficientBalance
from ledger.models import Asset, Trx
from ledger.utils.external_price import SELL, BUY
from ledger.utils.test import new_account, create_system_order_book
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol, Order
from market.utils.order_utils import new_order


class CreateOrderTestCase(TestCase):
    def setUp(self):
        PairSymbol.objects.filter(name='BTCUSDT').update(enable=True)
        Asset.objects.filter(symbol='BTC').update(enable=True)

    def test_time_in_force(self):
        btcusdt = PairSymbol.objects.get(name='BTCUSDT')
        account = new_account()
        usdt = Asset.get(Asset.USDT)
        system = Account.system()

        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                group_id=uuid4(),
                sender=usdt.get_wallet(system),
                receiver=usdt.get_wallet(account),
                amount=10000,
                scope=Trx.TRANSFER
            )

        create_system_order_book(btcusdt, SELL, [
            (20000, Decimal('0.2')),
            (21000, Decimal('0.3')),
            (22000, Decimal('0.3')),
        ])

        with WalletPipeline() as pipeline:
            fok_order = new_order(
                pipeline=pipeline,
                symbol=btcusdt,
                account=account,
                amount=Decimal('0.3'),
                price=Decimal(20500),
                side=BUY,
                time_in_force=Order.FOK
            )

        fok_order.refresh_from_db()
        self.assertEqual(fok_order.status, Order.CANCELED)
        self.assertEqual(fok_order.filled_amount, 0)

        self.assertEqual(Order.objects.aggregate(sum=Sum('filled_amount'))['sum'], 0)

        with WalletPipeline() as pipeline:
            ordinary_order = new_order(
                pipeline=pipeline,
                symbol=btcusdt,
                account=account,
                amount=Decimal('0.3'),
                price=Decimal(20500),
                side=BUY,
                time_in_force=Order.ORDINARY
            )

        ordinary_order.refresh_from_db()
        self.assertEqual(ordinary_order.status, Order.NEW)
        self.assertEqual(ordinary_order.filled_amount, Decimal('0.2'))

        self.assertEqual(Order.objects.aggregate(sum=Sum('filled_amount'))['sum'], Decimal('0.4'))

        try:
            with WalletPipeline() as pipeline:
                new_order(
                    pipeline=pipeline,
                    symbol=btcusdt,
                    account=account,
                    amount=Decimal('0.2'),
                    price=Decimal(22000),
                    side=BUY,
                    time_in_force=Order.FOK
                )
            self.fail('Should raise insufficient balance')
        except InsufficientBalance:
            pass

        with WalletPipeline() as pipeline:
            fok_order = new_order(
                pipeline=pipeline,
                symbol=btcusdt,
                account=account,
                amount=Decimal('0.1'),
                price=Decimal(22000),
                side=BUY,
                time_in_force=Order.FOK
            )

        fok_order.refresh_from_db()
        self.assertEqual(fok_order.status, Order.FILLED)
        self.assertEqual(fok_order.filled_amount, Decimal('0.1'))
