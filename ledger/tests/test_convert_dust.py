from decimal import Decimal

from django.test import Client
from django.test import TestCase

from ledger.models import Asset
from ledger.utils.test import new_account, set_price

BTC_USDT_PRICE = 20000
USDT_IRT_PRICE = 30000


class ConvertDustTestCase(TestCase):

    def setUp(self) -> None:
        self.account = new_account()
        user = self.account.user

        self.client = Client()
        self.client.force_login(user)

        self.btc = Asset.get('BTC')
        self.usdt = Asset.get('USDT')
        self.ada = Asset.get('ADA')
        self.irt = Asset.get('IRT')

        self.wallet_usdt = self.usdt.get_wallet(self.account)
        self.wallet_btc = self.btc.get_wallet(self.account)
        self.wallet_irt = self.irt.get_wallet(self.account)

        set_price(self.btc, BTC_USDT_PRICE)
        set_price(self.usdt, USDT_IRT_PRICE)

    def test_convert_dust_for_zero_wallet(self):
        resp = self.client.post('/api/v1/convert/dust/')

        self.assertEqual(resp.status_code, 400)

        self.assertEqual(self.wallet_irt.balance, 0)
        self.assertEqual(self.wallet_btc.balance, 0)
        self.assertEqual(self.wallet_usdt.balance, 0)

    def test_convert_dust(self):
        self.wallet_btc.airdrop(Decimal('.000001'))
        self.wallet_usdt.airdrop(Decimal('10'))
        self.wallet_irt.airdrop(Decimal('5000'))

        resp = self.client.post('/api/v1/convert/dust/')
        self.assertEqual(resp.status_code, 200)

        self.wallet_btc.refresh_from_db()
        self.wallet_usdt.refresh_from_db()
        self.wallet_irt.refresh_from_db()

        self.assertGreater(self.wallet_irt.balance, 5000)
        self.assertEqual(self.wallet_usdt.balance, 10)
        self.assertEqual(self.wallet_btc.balance, 0)
