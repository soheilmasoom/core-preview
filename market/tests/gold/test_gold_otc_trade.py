from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client, override_settings

from _base import settings
from _base.utils import ExchangeType
from accounts.models import Account, SystemConfig
from ledger.models import Asset, AssetSpreadCategory, CategorySpread, Trx, Wallet
from ledger.utils.external_price import USDT, BUY, SELL
from ledger.utils.test import new_account, set_price
from market.models import PairSymbol


@override_settings(SETTINGS_MODULE='test_settings')
class GoldOtcTradeTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        patcher = patch('decouple.config')
        mock_config = patcher.start()

        def config_side_effect(key, **kwargs):
            if key == 'EXCHANGE_TYPE':
                return 'PRECIOUS_METALS'
            return kwargs.get('default')

        mock_config.side_effect = config_side_effect

        settings.EXCHANGE_TYPE = ExchangeType(config_side_effect('EXCHANGE_TYPE', default='PRECIOUS_METALS'))

        super().setUpClass()
        cls.patcher = patcher

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        super().tearDownClass()

    def setUp(self):
        category = AssetSpreadCategory.objects.create(name='تک نرخی')
        CategorySpread.objects.create(side=BUY, category=category, spread=0, step=1)
        CategorySpread.objects.create(side=SELL, category=category, spread=0, step=1)

        self.xaum = Asset.objects.create(symbol='XAUM', name='XAUM', enable=True, external_price_symbol='xaum',
                                         otc_status=Asset.ACTIVE, spread_category=category)
        self.irt = Asset.get(Asset.IRT)
        self.irt.enable = True
        self.irt.save()

        self.xaumirt = PairSymbol.objects.create(name='XAUMIRT', enable=False, asset=self.xaum, base_asset=self.irt,
                                                 step_size=0, tick_size=0, min_trade_quantity=1)
        self.account = new_account()

        set_price(self.xaum, 5_230_000, 5_230_000, base='irt')  # 1 gram price
        set_price(Asset.get(Asset.USDT), 80_000, 80_000)

        self.wallet_irt = self.irt.get_wallet(self.account)
        self.wallet_xaum = self.xaum.get_wallet(self.account)

        self.system_wallet_irt = self.irt.get_wallet(Account.system())
        self.system_wallet_xaum = self.xaum.get_wallet(Account.system())
        SystemConfig.objects.create(name='main', active=True, commission_type=SystemConfig.FEE_ADD_PAYING)
        self.client = Client()
        self.client.force_login(self.account.user)

    def test_error(self):
        self.xaum.otc_status = Asset.DISABLED
        self.xaum.save()
        self.wallet_irt.airdrop(100_000)
        self.wallet_xaum.airdrop(50)
        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "IRT", "to_asset": "XAUM", "to_amount": "2"})
        print(response.data)

    def test_otc_requests(self):
        self.wallet_irt.airdrop(100_000)
        self.wallet_xaum.airdrop(50)
        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "IRT", "to_asset": "XAUM", "to_amount": "2"})

        self.assert_otc_request(
            data=response.data,
            price='5230',
            fee='21',
            paying_amount=Decimal('10481'),
            receiving_amount=Decimal('2'),
            net_receiving_amount=Decimal('2')
        )

        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "IRT", "to_asset": "XAUM", "from_amount": "40000"})
        self.assert_otc_request(
            data=response.data,
            price='5230',
            fee='74',
            paying_amount=Decimal('36684'),
            receiving_amount=Decimal('7'),
            net_receiving_amount=Decimal('7')
        )

        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "XAUM", "to_asset": "IRT", "from_amount": "5"})
        self.assert_otc_request(
            data=response.data,
            price='5230',
            fee='53',
            paying_amount=Decimal('5'),
            receiving_amount=Decimal('26150'),
            net_receiving_amount=Decimal('26097')
        )

        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "XAUM", "to_asset": "IRT", "to_amount": "50000"})
        self.assert_otc_request(
            data=response.data,
            price='5230',
            fee='95',
            paying_amount=Decimal('9'),
            receiving_amount=Decimal('47070'),
            net_receiving_amount=Decimal('46975')
        )

    def test_buy(self):
        self.wallet_irt.airdrop(100_000)
        self.wallet_xaum.airdrop(50)

        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "IRT", "to_asset": "XAUM", "to_amount": "2"})

        token = response.data['token']
        response = self.client.post('/api/v1/trade/otc/', {"token": token})
        self.assertEqual(response.data['status'], 'done')

        self.wallet_xaum.refresh_from_db()
        self.wallet_irt.refresh_from_db()
        self.assertEqual(self.wallet_xaum.balance, Decimal('52'))
        self.assertEqual(self.wallet_irt.balance, Decimal('89519'))

    def test_sell_with_from_amount(self):
        self.wallet_xaum.airdrop(50)

        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "XAUM", "to_asset": "IRT", "from_amount": "9"})
        self.assert_otc_request(
            data=response.data,
            price='5230',
            fee='95',
            paying_amount=Decimal('9'),
            receiving_amount=Decimal('47070'),
            net_receiving_amount=Decimal('46975')
        )
        token = response.data['token']
        response = self.client.post('/api/v1/trade/otc/', {"token": token})

        self.assertEqual(response.data['status'], 'done')

        self.wallet_xaum.refresh_from_db()
        self.wallet_irt.refresh_from_db()
        self.assertEqual(self.wallet_xaum.balance, Decimal('41'))
        self.assertEqual(self.wallet_irt.balance, Decimal('46975'))

    def test_sell_with_to_amount(self):
        self.wallet_xaum.airdrop(50)

        response = self.client.post('/api/v1/trade/otc/request/',
                                    {"from_asset": "XAUM", "to_asset": "IRT", "to_amount": "50000"})

        token = response.data['token']
        response = self.client.post('/api/v1/trade/otc/', {"token": token})

        self.assertEqual(response.data['status'], 'done')

        self.wallet_xaum.refresh_from_db()
        self.wallet_irt.refresh_from_db()
        self.assertEqual(self.wallet_xaum.balance, Decimal('41'))
        self.assertEqual(self.wallet_irt.balance, Decimal('46975'))

    def assert_otc_request(self, data, price, fee, paying_amount, receiving_amount, net_receiving_amount):
        self.assertEqual(data['price'], price, f"Expected price {price}, got {data['price']}")
        self.assertEqual(data['fee'], fee, f"Expected fee {fee}, got {data['fee']}")
        self.assertEqual(Decimal(data['paying_amount']), paying_amount,
                         f"Expected paying_amount {paying_amount}, got {data['paying_amount']}")
        self.assertEqual(Decimal(data['receiving_amount']), receiving_amount,
                         f"Expected receiving_amount {receiving_amount}, got {data['receiving_amount']}")
        self.assertEqual(Decimal(data['net_receiving_amount']), net_receiving_amount,
                         f"Expected net_receiving_amount {net_receiving_amount}, got {data['net_receiving_amount']}")
