import os
from unittest.mock import patch

from decouple import config
from django.test import TestCase, Client, override_settings

from _base import settings
from _base.utils import ExchangeType
from accounts.models import Account
from ledger.models import Asset, AssetSpreadCategory, CategorySpread
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
        self.client = Client()
        self.client.force_login(self.account.user)

        set_price(self.xaum, 5_000_000, 5_000_000, base='irt')  # 1 gram price
        set_price(Asset.get(Asset.USDT), 80_000, 80_000)

        self.wallet_irt = self.irt.get_wallet(self.account)
        self.wallet_xaum = self.xaum.get_wallet(self.account)

        self.system_wallet_irt = self.irt.get_wallet(Account.system())
        self.system_wallet_xaum = self.xaum.get_wallet(Account.system())

    def test_1(self):
        print(settings.EXCHANGE_TYPE)
        self.wallet_irt.airdrop(100_000)
        a = self.client.post('/api/v1/trade/otc/request/',
                             {"from_asset": "IRT", "to_asset": "XAUM", "to_amount": "2"})
        print(a.data)
