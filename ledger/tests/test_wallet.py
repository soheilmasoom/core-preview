from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError
from django.test import TestCase

from accounts.models import Account
from ledger.models import Asset, Trx, BalanceLock
from ledger.utils.test import new_account
from ledger.utils.wallet_pipeline import WalletPipeline


class WalletTestCase(TestCase):
    def setUp(self):
        self.account = new_account()
        self.account2 = new_account()
        self.irt = Asset.get(Asset.IRT)
        self.usdt = Asset.get(Asset.USDT)
        self.wallet = self.usdt.get_wallet(self.account)
        self.wallet2 = self.usdt.get_wallet(self.account2)
        self.system_wallet = self.usdt.get_wallet(Account.system())

    def test_transaction(self):
        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=self.system_wallet,
                receiver=self.wallet,
                amount=1,
                scope=Trx.TRANSFER,
                group_id=uuid4()
            )

        self.assertEqual(self.wallet.balance, 1)
        self.assertEqual(self.wallet.locked, 0)
        self.assertEqual(self.system_wallet.balance, -1)

        self.wallet.refresh_from_db()
        self.system_wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 1)
        self.assertEqual(self.wallet.locked, 0)
        self.assertEqual(self.system_wallet.balance, -1)

        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=self.wallet,
                receiver=self.system_wallet,
                amount=1,
                scope=Trx.TRANSFER,
                group_id=uuid4()
            )

        self.assertEqual(self.wallet.balance, 0)
        self.assertEqual(self.wallet.locked, 0)
        self.assertEqual(self.system_wallet.balance, 0)

        self.wallet.refresh_from_db()
        self.system_wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 0)
        self.assertEqual(self.wallet.locked, 0)
        self.assertEqual(self.system_wallet.balance, 0)

        try:
            with WalletPipeline() as pipeline:
                pipeline.new_trx(
                    sender=self.wallet,
                    receiver=self.system_wallet,
                    amount=5,
                    scope=Trx.TRANSFER,
                    group_id=uuid4()
                )

            self.fail('Should fail here!')
        except IntegrityError:
            pass

        checkpoint = False

        try:
            with WalletPipeline() as pipeline:
                pipeline.new_trx(
                    sender=self.system_wallet,
                    receiver=self.wallet,
                    amount=1,
                    scope=Trx.TRANSFER,
                    group_id=uuid4()
                )

                checkpoint = True

                pipeline.new_trx(
                    sender=self.wallet2,
                    receiver=self.wallet,
                    amount=10,
                    scope=Trx.TRANSFER,
                    group_id=uuid4()
                )

                self.fail('should fail here')

        except IntegrityError:
            pass

        self.assertTrue(checkpoint)

        self.wallet.refresh_from_db()
        self.wallet2.refresh_from_db()
        self.system_wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 0)
        self.assertEqual(self.wallet.locked, 0)
        self.assertEqual(self.wallet2.balance, 0)
        self.assertEqual(self.wallet2.locked, 0)
        self.assertEqual(self.system_wallet.balance, 0)

    def test_lock(self):
        with WalletPipeline() as pipeline:
            pipeline.new_trx(
                sender=self.system_wallet,
                receiver=self.wallet,
                amount=10,
                scope=Trx.TRANSFER,
                group_id=uuid4()
            )

        self.assertEqual(self.wallet.balance, 10)
        self.assertEqual(self.wallet.locked, 0)
        self.assertEqual(self.system_wallet.balance, -10)

        self.wallet.refresh_from_db()
        self.system_wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 10)
        self.assertEqual(self.wallet.locked, 0)

        lock_key = uuid4()

        with WalletPipeline() as pipeline:
            pipeline.new_lock(key=lock_key, wallet=self.wallet, amount=4, reason=WalletPipeline.TRADE)

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 10)
        self.assertEqual(self.wallet.locked, 4)

        with WalletPipeline(verbose=True) as pipeline:
            pipeline.release_lock(key=lock_key, amount=2)

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 10)
        self.assertEqual(self.wallet.locked, 2)

        with WalletPipeline(verbose=True) as pipeline:
            pipeline.release_lock(key=lock_key)

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 10)
        self.assertEqual(self.wallet.locked, 0)

        with WalletPipeline(verbose=True) as pipeline:
            pipeline.release_lock(key=lock_key)

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, 10)
        self.assertEqual(self.wallet.locked, 0)

        try:
            with WalletPipeline(verbose=True) as pipeline:
                pipeline.release_lock(key=lock_key, amount=2)

            self.fail('should fail here')
        except:
            pass

    def test_double_new_trx(self):
        sender = self.usdt.get_wallet(new_account())
        receiver = self.usdt.get_wallet(new_account())

        sender.airdrop(20)

        group_id = uuid4()

        with WalletPipeline() as pipeline:
            pipeline.new_trx(sender, receiver, 10, Trx.TRANSFER, group_id=group_id)
            pipeline.new_trx(sender, receiver, 5, Trx.TRANSFER, group_id=group_id)

        sender.refresh_from_db()
        receiver.refresh_from_db()

        self.assertEqual(sender.balance, 5)
        self.assertEqual(receiver.balance, 15)

    def test_trade_simulation(self):
        acc1 = new_account()
        acc2 = new_account()
        acc3 = new_account()
        wallet_irt1 = self.irt.get_wallet(acc1)
        wallet_usdt1 = self.usdt.get_wallet(acc1)
        
        wallet_irt2 = self.irt.get_wallet(acc2)
        wallet_usdt2 = self.usdt.get_wallet(acc2)
        
        wallet_irt3 = self.irt.get_wallet(acc3)
        wallet_usdt3 = self.usdt.get_wallet(acc3)

        wallet_irt1.airdrop(3)
        wallet_usdt2.airdrop(2000)

        lock_key0 = uuid4()

        lock_key1 = uuid4()
        lock_key2 = uuid4()

        with WalletPipeline() as pipeline:
            pipeline.new_lock(lock_key0, wallet_usdt2, amount=1800, reason=WalletPipeline.TRADE)

        with WalletPipeline() as pipeline:
            pipeline.new_lock(lock_key1, wallet_irt1, amount=2, reason=WalletPipeline.TRADE)

        with WalletPipeline() as pipeline:
            pipeline.new_lock(lock_key2, wallet_irt1, amount=1, reason=WalletPipeline.TRADE)

        with WalletPipeline() as pipeline:
            pipeline.release_lock(lock_key1)
            pipeline.release_lock(lock_key0, 1200)
            trade_key = uuid4()
            pipeline.new_trx(wallet_usdt2, wallet_usdt1, 1200, Trx.TRADE, trade_key)
            pipeline.new_trx(wallet_irt1, wallet_irt2, 2, Trx.TRADE, trade_key)
            pipeline.new_trx(wallet_usdt1, wallet_usdt3, Decimal('2.4'), Trx.COMMISSION, trade_key)
            pipeline.new_trx(wallet_irt2, wallet_irt3, 0, Trx.COMMISSION, trade_key)

            pipeline.release_lock(lock_key2)
            pipeline.release_lock(lock_key0, 600)
            trade_key = uuid4()
            pipeline.new_trx(wallet_usdt2, wallet_usdt1, 600, Trx.TRADE, trade_key)
            pipeline.new_trx(wallet_irt1, wallet_irt2, 37130400, Trx.TRADE, trade_key)
            pipeline.new_trx(wallet_usdt1, wallet_usdt3, Decimal('1.2'), Trx.COMMISSION, trade_key)
            pipeline.new_trx(wallet_irt2, wallet_irt3, 0, Trx.COMMISSION, trade_key)

