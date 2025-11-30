from decimal import Decimal

from django.test import TestCase

from accounts.models import Account, Referral
from accounts.utils.test import create_referral, set_referred_by
from ledger.models import Trx, Asset, OTCRequest
from ledger.utils.external_price import BUY, SELL
from ledger.utils.test import new_account, set_price
from ledger.utils.wallet_pipeline import WalletPipeline
from market.models import PairSymbol, Trade, BaseTrade
from market.models.pair_symbol import DEFAULT_TAKER_FEE
from market.utils.order_utils import new_order
from market.utils.trade import get_fee_info


class ReferralTestCase(TestCase):
    def init_accounts(self):
        account_1 = new_account()
        account_1_referral = create_referral(account_1)
        account_2 = new_account()
        account_3 = new_account()
        set_referred_by(account_3, account_1_referral)
        account_3.save()
        self.btc.get_wallet(account_2).airdrop(1000 * 1000 * 1000)
        self.irt.get_wallet(account_3).airdrop(1000 * 1000 * 1000)
        self.usdt.get_wallet(account_3).airdrop(1000 * 1000 * 1000)
        return account_1, account_2, account_3, account_1_referral

    def setUp(self):
        PairSymbol.objects.filter(name='BTCIRT').update(enable=True)
        PairSymbol.objects.filter(name='BTCUSDT').update(enable=True)

        self.irt = Asset.get(Asset.IRT)
        self.btc = Asset.get('BTC')
        self.usdt = Asset.get('USDT')
        self.btcitr = PairSymbol.objects.get(name='BTCIRT')
        self.btcusdt = PairSymbol.objects.get(name='BTCUSDT')
        self.usdtirt = PairSymbol.objects.get(name='USDTIRT')

        set_price(self.btc, 30000)

    def test_referral_btc_irt(self):
        account_1, account_2, account_3, account_1_referral = self.init_accounts()
        with WalletPipeline() as pipeline:
            order_1 = new_order(pipeline, self.btcitr, account_2, SELL, 2, 200000, )
            order_2 = new_order(pipeline, self.btcitr, account_3, BUY, 2, 200005)

        order_1.refresh_from_db(), order_2.refresh_from_db()

        trade = Trade.objects.get(order_id=order_1.id)

        trx_referral = Trx.objects.get(
            group_id=trade.group_id,
            sender=self.irt.get_wallet(Account.system()),
            receiver=self.irt.get_wallet(account_1),
            scope=Trx.COMMISSION
        )
        fee_trx_referred = Trx.objects.get(
            group_id=trade.group_id,
            sender=self.btc.get_wallet(account_3),
            receiver=self.btc.get_wallet(Account.system()),
            scope=Trx.COMMISSION
        )
        self.assertEqual(
            trx_referral.amount,
            account_1_referral.owner_share_percent / Decimal('100') *
            DEFAULT_TAKER_FEE * trade.amount * trade.price
        )
        self.assertEqual(
            fee_trx_referred.amount,
            (1 - ((Referral.REFERRAL_MAX_RETURN_PERCENT - account_1_referral.owner_share_percent) / Decimal(
                '100'))) *
            DEFAULT_TAKER_FEE * trade.amount
        )

    def test_referral_btc_usdt(self):
        set_price(self.usdt, 1)
        set_price(self.btc, 25000)
        account_1, account_2, account_3, account_1_referral = self.init_accounts()
        with WalletPipeline() as pipeline:
            order_3 = new_order(pipeline, self.btcusdt, account_2, SELL, 2, 200000)
            order_4 = new_order(pipeline, self.btcusdt, account_3, BUY, 2, 200000)

        order_3.refresh_from_db(), order_4.refresh_from_db()

        trade = Trade.objects.get(order_id=order_3.id)

        trx_referral = Trx.objects.get(
            group_id=trade.group_id,
            sender=self.irt.get_wallet(Account.system()),
            receiver=self.irt.get_wallet(account_1),
            scope=Trx.COMMISSION
        )

        fee_trx_referred = Trx.objects.get(
            group_id=trade.group_id,
            sender=self.btc.get_wallet(account_3),
            receiver=self.btc.get_wallet(Account.system()),
            scope=Trx.COMMISSION
        )
        self.assertEqual(
            trx_referral.amount,
            account_1_referral.owner_share_percent / Decimal('100') *
            DEFAULT_TAKER_FEE * trade.amount * trade.price
        )
        self.assertEqual(
            fee_trx_referred.amount,
            (1 - ((Referral.REFERRAL_MAX_RETURN_PERCENT - account_1_referral.owner_share_percent) / Decimal(
                '100'))) *
            DEFAULT_TAKER_FEE * trade.amount
        )

    def test_referral_usdt_irt(self):
        account_1, _, account_3, account_1_referral = self.init_accounts()
        account_3.print()
        with WalletPipeline() as pipeline:
            order_5 = new_order(pipeline, self.usdtirt, Account.system(), BUY, 20, 20000)
            order_6 = new_order(pipeline, self.usdtirt, account_3, SELL, 20, 20000)

            order_7 = new_order(pipeline, self.usdtirt, Account.system(), SELL, 10, 20000)
            order_8 = new_order(pipeline, self.usdtirt, account_3, BUY, 10, 20000)

        order_5.refresh_from_db(), order_6.refresh_from_db(), order_7.refresh_from_db(), order_8.refresh_from_db()

        trade = Trade.objects.get(order_id=order_5.id)
        trade_2 = Trade.objects.get(order_id=order_7.id)

        trx_referral = Trx.objects.get(
            group_id=trade.group_id,
            sender=self.irt.get_wallet(Account.system()),
            receiver=self.irt.get_wallet(account_1),
            scope=Trx.COMMISSION
        )
        fee_trx_referred = Trx.objects.get(
            group_id=trade.group_id,
            sender=self.irt.get_wallet(account_3),
            receiver=self.irt.get_wallet(Account.system()),
            scope=Trx.COMMISSION
        )

        trx_referral_2 = Trx.objects.get(
            group_id=trade_2.group_id,
            sender=self.irt.get_wallet(Account.system()),
            receiver=self.irt.get_wallet(account_1),
            scope=Trx.COMMISSION
        )
        fee_trx_referred_2 = Trx.objects.get(
            group_id=trade_2.group_id,
            sender=self.usdt.get_wallet(account_3),
            receiver=self.usdt.get_wallet(Account.system()),
            scope=Trx.COMMISSION
        )
        self.assertEqual(
            trx_referral.amount,
            account_1_referral.owner_share_percent / Decimal('100') *
            DEFAULT_TAKER_FEE * trade.amount * trade.price
        )

        self.assertEqual(
            fee_trx_referred.amount,
            (1 - ((Referral.REFERRAL_MAX_RETURN_PERCENT - account_1_referral.owner_share_percent) / Decimal(
                '100'))) *
            DEFAULT_TAKER_FEE * trade.amount * trade.price
        )

        self.assertEqual(
            trx_referral_2.amount,
            account_1_referral.owner_share_percent / Decimal('100') *
            DEFAULT_TAKER_FEE * trade_2.amount * trade_2.price
        )

        self.assertEqual(
            fee_trx_referred_2.amount,
            (1 - ((Referral.REFERRAL_MAX_RETURN_PERCENT - account_1_referral.owner_share_percent) / Decimal(
                '100'))) *
            DEFAULT_TAKER_FEE * trade_2.amount
        )

    def test_fee_info(self):
        s = PairSymbol.objects.create(
            name='TESTUSDT',
            asset=Asset.objects.create(symbol='TEST'),
            base_asset=self.usdt,
            custom_taker_fee=Decimal('0.003'),
            custom_maker_fee=Decimal('0')
        )

        referrer = Account.objects.create()
        ref = Referral.objects.create(owner=referrer, owner_share_percent=20)
        a = Account.objects.create(referred_by=ref)

        trade = Trade(
            side=BUY,
            amount=100,
            price=3000,
            is_maker=True,
            symbol=s,
            account=a,
            base_irt_price=40000,
            base_usdt_price=1
        )

        info = get_fee_info(trade)
        self.assertEqual(info.trader_fee_amount, 0)
        self.assertEqual(info.trader_fee_value, 0)
        self.assertEqual(info.fee_revenue, 0)
        self.assertEqual(info.referrer_reward_irt, 0)

        trade.side = SELL
        info = get_fee_info(trade)
        self.assertEqual(info.trader_fee_amount, 0)
        self.assertEqual(info.trader_fee_value, 0)
        self.assertEqual(info.fee_revenue, 0)
        self.assertEqual(info.referrer_reward_irt, 0)

        trade.is_maker = False
        trade.side = BUY
        info = get_fee_info(trade)
        self.assertEqual(info.trader_fee_amount, Decimal('0.27'))
        self.assertEqual(info.trader_fee_value, Decimal('810'))
        self.assertEqual(info.fee_revenue, Decimal('630'))
        self.assertEqual(info.referrer_reward_irt, Decimal('7200000'))

        trade.side = SELL
        info = get_fee_info(trade)
        self.assertEqual(info.trader_fee_amount, Decimal('810'))
        self.assertEqual(info.trader_fee_value, Decimal('810'))
        self.assertEqual(info.fee_revenue, Decimal('630'))
        self.assertEqual(info.referrer_reward_irt, Decimal('7200000'))
