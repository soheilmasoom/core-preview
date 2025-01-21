from django.test import TestCase

from ledger.models import ManualWithdraw, ManualAddressBook, Asset
from ledger.utils.fields import INIT
from ledger.utils.test import set_price, new_network_asset, new_network


class ManualWithdrawTestCase(TestCase):
    def setUp(self):
        self.btc = Asset.get('BTC')

        set_price(self.btc, 30000)

        self.btc_network = new_network(symbol='BTC')
        new_network_asset(asset=self.btc, network=self.btc_network)

        self.address_book = ManualAddressBook.objects.create(
            name="Test Address Book",
            address="0x1234567890abcdef1234567890abcdef12345678",
            network=self.btc_network,
            memo="Test Memo"
        )

        self.manual_withdraw = ManualWithdraw.objects.create(
            address_book=self.address_book,
            asset=self.btc,
            amount=1.5,
            comment="Test Comment",
        )

    def test_manual_withdraw_processing(self):
        self.assertEqual(self.manual_withdraw.status, INIT)
        self.assertEqual(self.manual_withdraw.address_book.address, self.address_book.address)
        self.assertEqual(self.manual_withdraw.address_book.network.symbol, self.address_book.network.symbol)
        self.assertEqual(self.manual_withdraw.address_book.memo, self.address_book.memo)
