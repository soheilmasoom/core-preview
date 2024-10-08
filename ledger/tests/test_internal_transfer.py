from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, Account
from ledger.models import Asset, InternalTransfer, Wallet
from ledger.utils.test import new_account, set_price
from accounts.utils.login import set_login_activity
from market.models import PairSymbol


class InternalTransferTestCase(TestCase):
    def setUp(self):
        self.account1 = new_account()
        self.account2 = new_account()
        self.user1 = self.account1.user
        self.user2 = self.account2.user
        self.user2.phone = "09121231234"
        self.user2.level = User.LEVEL2
        self.user1.level = User.LEVEL2
        self.user2.save()

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
        self.wallet_usdt.airdrop(10)

        url = "/api/v1/internal-transfers/"
        data = {
            'receiver_phone': "09121231234",
            'asset': 'USDT',
            'amount': '10',
            'description': 'Test transfer',
            'code': "1111"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(InternalTransfer.objects.count(), 1)
        transfer = InternalTransfer.objects.first()
        self.assertEqual(transfer.sender_account, self.account1)
        self.assertEqual(transfer.receiver_account, self.account2)
        self.assertEqual(transfer.amount, Decimal('10'))
        self.assertEqual(transfer.asset, self.usdt)
