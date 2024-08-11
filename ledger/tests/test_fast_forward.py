from decimal import Decimal
from unittest import mock

from django.test import TestCase

from ledger.models import Transfer, DepositAddress, Trx, Asset, AddressKey, Network
from ledger.utils.test import new_account, set_price


class FastForwardTestCase(TestCase):
    def new_network(self) -> Network:
        return Network.objects.create(
            symbol='ETH',
            name='ETH',
            address_regex=r'\w+'
        )

    def new_memo_network(self) -> Network:
        return Network.objects.create(
            symbol='XRP',
            name='XRP',
            address_regex=r'\w+',
            deposit_need_memo=True,
            withdraw_allow_memo=True
        )

    def setUp(self) -> None:
        self.network = self.new_network()
        self.network2 = self.new_memo_network()
        self.asset, _ = Asset.objects.get_or_create(symbol=self.network.symbol)
        self.asset2, _ = Asset.objects.get_or_create(symbol=self.network2.symbol)
        set_price(self.asset, 19000)

        self.sender_account1 = new_account()
        self.sender_address_key1 = AddressKey.objects.create(account=self.sender_account1, address='0xC8E19189888BED6aaBf88800024106eC7C8cb00B', architecture='ETH')
        self.sender_deposit_address1 = DepositAddress.objects.create(
            # account=self.sender_account1,
            network=self.network,
            address_key=self.sender_address_key1,
            address='0xC8E19189888BED6aaBf88800024106eC7C8cb00B'
        )
        self.sender_wallet1 = self.asset.get_wallet(account=self.sender_account1)
        self.sender_wallet1.balance = 10
        self.sender_wallet1.save()

        self.sender_account2 = new_account()
        self.sender_address_key2 = AddressKey.objects.create(account=self.sender_account2,
                                                             address='xrp123',
                                                             architecture='XRP',
                                                             memo='2')
        self.sender_deposit_address2 = DepositAddress.objects.create(
            # account=self.sender_account1,
            network=self.network2,
            address_key=self.sender_address_key2,
            address='xrp123'
        )
        self.sender_wallet2 = self.asset2.get_wallet(account=self.sender_account2)
        self.sender_wallet2.balance = 10
        self.sender_wallet2.save()

        self.receiver_account1 = new_account()
        self.receiver_address_key1 = AddressKey.objects.create(account=self.receiver_account1, address='0x701e0e2f85E3922F50C054d113b9D694c675a7f5', architecture='ETH')
        self.receiver_deposit_address1 = DepositAddress.objects.create(
            # account=self.receiver_account1,
            network=self.network,
            address_key=self.receiver_address_key1,
            address='0x701e0e2f85E3922F50C054d113b9D694c675a7f5'
        )
        self.receiver_wallet1 = self.asset.get_wallet(account=self.receiver_account1)

        self.receiver_account2 = new_account()
        self.receiver_address_key2 = AddressKey.objects.create(account=self.receiver_account2, address='xrp1234', architecture='XRP', memo='1')
        self.receiver_deposit_address2 = DepositAddress.objects.create(
            # account=self.receiver_account1,
            network=self.network2,
            address_key=self.receiver_address_key2,
            address='xrp1234'
        )
        self.receiver_wallet2 = self.asset2.get_wallet(account=self.receiver_account2)

    def test_fast_forward1(self):
        Transfer.check_fast_forward(
            sender_wallet=self.sender_wallet1,
            network=self.network,
            amount=Decimal(1),
            address=self.receiver_deposit_address1.address
        )

        self.assertEqual(
            Trx.objects.get(sender=self.sender_wallet1).group_id,
            Transfer.objects.get(deposit_address=self.receiver_deposit_address1).group_id)

    def test_fast_forward2(self):

        transfer = Transfer.check_fast_forward(
            sender_wallet=self.sender_wallet1,
            network=self.network,
            amount=Decimal(1),
            address='0x6D3251369E08248f7a37355E497682Fd465767fb'
        )

        self.assertEqual(transfer, None)

    def test_fast_forward3(self):
        Transfer.check_fast_forward(
            sender_wallet=self.sender_wallet2,
            network=self.network2,
            amount=Decimal(1),
            address=self.receiver_deposit_address2.address,
            memo='1'
        )

        self.assertEqual(
            Trx.objects.get(sender=self.sender_wallet2).group_id,
            Transfer.objects.get(deposit_address=self.receiver_deposit_address2).group_id)

    def test_fast_forward4(self):
        transfer = Transfer.check_fast_forward(
            sender_wallet=self.sender_wallet2,
            network=self.network2,
            amount=Decimal(1),
            address=self.receiver_deposit_address2.address,
            memo='mamadasd'
        )

        self.assertEqual(transfer, None)

    def test_fast_forward5(self):
        transfer = Transfer.check_fast_forward(
            sender_wallet=self.sender_wallet2,
            network=self.network2,
            amount=Decimal(2),
            address='mamadssd',
            memo='1'
        )

        self.assertEqual(transfer, None)
