from django.test import TestCase, Client
from rest_framework import status
from decimal import Decimal

from accounts.models import User, Account
from ledger.models import Asset
from ledger.models.transfer import Transfer
from ledger.utils.test import new_account, set_price
from market.models import PairSymbol
from ledger.utils.test import new_account, generate_otp_code
from accounts.utils.mask import get_masked_phone


class InternalTransferTestCase(TestCase):
    def setUp(self):
        self.account1 = new_account()
        self.account2 = new_account()
        self.user1 = self.account1.user
        self.user2 = self.account2.user
        self.user2.phone = "09121231234"
        self.user2.level = User.LEVEL2
        self.user1.level = User.LEVEL2
        self.user1.custom_crypto_withdraw_ceil = 1000000000
        self.user2.custom_crypto_withdraw_ceil = 1000000000
        self.user2.save()
        self.user1.save()

        self.client = Client()
        self.client.force_login(self.user1)


        self.irt = Asset.get(Asset.IRT)
        self.usdt = Asset.get(Asset.USDT)
        self.btc = Asset.get('BTC')

        self.symbol = PairSymbol.objects.get(asset=self.btc, base_asset=self.usdt)

        set_price(self.usdt, 30000)  # IRT
        set_price(self.btc, 30000)  # USDT

        self.wallet_irt = self.irt.get_wallet(self.account1)
        self.wallet_usdt = self.usdt.get_wallet(self.account1)
        self.wallet_btc = self.btc.get_wallet(self.account1)

        self.system_wallet_usdt = self.usdt.get_wallet(Account.system())
        self.system_wallet_btc = self.btc.get_wallet(Account.system())


    def test_create_internal_transfer(self):
        self.wallet_usdt.airdrop(1)

        url = "/api/v1/withdraw/"
        data = {
            'source': "internal_account",
            'address': "09121231234",
            'coin': 'USDT',
            'amount': '1',
            'description': 'Test transfer',
            'code': generate_otp_code(self.user1, 'withdraw')
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transfer.objects.count(), 1)
        transfer = Transfer.objects.first()
        self.assertEqual(transfer.wallet, transfer.asset.get_wallet(self.account1))
        self.assertEqual(transfer.out_address,  get_masked_phone(self.account2.user.username))
        self.assertEqual(transfer.amount, Decimal('1'))
        self.assertEqual(transfer.asset, self.usdt)
        self.assertEqual(transfer.receiver_account, self.account2)
        self.assertEqual(transfer.status, 'process')

