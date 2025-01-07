from decimal import Decimal

from django.test import Client
from django.test import TestCase

from accounts.models import User
from accounts.utils.login import set_login_activity
from accounts.utils.mask import get_masked_phone
from ledger.models import Asset, AddressBook, Transfer
from ledger.utils.precision import get_presentation_amount
from ledger.utils.test import new_account, new_address_book, generate_otp_code, new_network, new_network_asset


class WithdrawTestCase(TestCase):
    def setUp(self):
        self.account = new_account()
        self.user = self.account.user
        self.user.level = User.LEVEL2
        self.user.save()
        self.client = Client()
        self.client.force_login(self.user)
        self.network = new_network()

        self.dest_account = new_account()
        self.dest_user = self.dest_account.user
        self.dest_user.phone = '09123456789'
        self.dest_user.level = User.LEVEL2
        self.dest_user.save(update_fields=['phone', 'level'])
        self.phone_address_book = new_address_book(
            address=self.dest_user.phone,
            account=self.account,
            dest_user=self.dest_user,
            address_type=AddressBook.TYPE_INTERNAL
        )
        self.normal_address_book = new_address_book(
            account=self.account,
            network=self.network,
            asset='USDT'
        )
        self.general_address_book = new_address_book(
            account=self.account,
            network=self.network
        )
        self.normal_whitelist_address_book = new_address_book(
            account=self.account,
            network=self.network,
            asset='USDT',
            whitelist=True
        )
        self.general_whitelist_address_book = new_address_book(
            account=self.account,
            network=self.network,
            whitelist=True
        )
        self.usdt = Asset.get(Asset.USDT)

        new_network_asset(self.usdt, self.network)

        self.usdt.get_wallet(self.user.get_account()).airdrop(100000)

        setattr(self.client, 'META', {'REMOTE_ADDR': '127.0.0.1'})
        set_login_activity(self.client, self.user, client_info={})  # to enable address book withdrawing

    def assert_expected_transfer(self, transfer_id, amount, out_address=None, receiver_account=None, asset=None,
                                 address_book=None, account=None, network=None):
        transfer = Transfer.objects.filter(id=transfer_id)
        self.assertEqual(len(transfer), 1)
        transfer = transfer[0]
        self.assertEqual(transfer.amount, Decimal(amount))
        self.assertEqual(transfer.receiver_account, receiver_account)
        self.assertEqual(transfer.asset, asset)
        self.assertEqual(transfer.address_book, address_book)
        self.assertEqual(transfer.wallet.account, account)
        self.assertEqual(transfer.network, network)
        self.assertEqual(transfer.out_address, out_address)

    def test_withdraw_without_addressbook(self):
        amount = '50'
        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'address': '123',
            'coin': 'USDT',
            'network': 'BSC',
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'address': '123',
            'coin': 'USDT',
            'network': 'BSC',
            'code': generate_otp_code(self.user, 'withdraw')
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual((get_presentation_amount(resp.data['amount'])), amount)
        self.assert_expected_transfer(
            transfer_id=resp.data['id'],
            amount=amount,
            out_address='123',
            network=self.network,
            asset=self.usdt,
            account=self.account
        )

    def test_normal_addressbook(self):
        amount = '50'

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'coin': 'BTC',
            'code': generate_otp_code(self.user, 'withdraw'),
            'address_book_id': self.normal_address_book.id
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'coin': 'USDT',
            'code': generate_otp_code(self.user, 'withdraw'),
            'address_book_id': self.normal_address_book.id
        })
        self.assertEqual(resp.status_code, 201)
        self.assert_expected_transfer(
            network=self.network,
            transfer_id=resp.data['id'],
            amount=amount,
            out_address=self.normal_address_book.address,
            asset=self.usdt,
            account=self.account,
            address_book=self.normal_address_book
        )

    def test_general_addressbook(self):
        amount = '50'
        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'code': generate_otp_code(self.user, 'withdraw'),
            'address_book_id': self.general_address_book.id
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'code': generate_otp_code(self.user, 'withdraw'),
            'coin': 'USDT',
            'address_book_id': self.general_address_book.id
        })
        self.assertEqual(resp.status_code, 201)
        self.assert_expected_transfer(
            network=self.network,
            transfer_id=resp.data['id'],
            amount=amount,
            out_address=self.general_address_book.address,
            asset=self.usdt,
            account=self.account,
            address_book=self.general_address_book
        )

    def test_otp_requirement(self):
        amount = '50'

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'coin': 'USDT',
            'address_book_id': self.general_address_book.id
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'coin': 'USDT',
            'address_book_id': self.general_whitelist_address_book.id
        })
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'coin': 'USDT',
            'address_book_id': self.normal_address_book.id
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'coin': 'USDT',
            'address_book_id': self.normal_whitelist_address_book.id
        })
        self.assertEqual(resp.status_code, 201)

    def test_phone_address_book(self):
        amount = '50'
        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'code': generate_otp_code(self.user, 'withdraw'),
            'address_book_id': self.phone_address_book.id
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'code': generate_otp_code(self.user, 'withdraw'),
            'coin': 'USDT',
            'address_book_id': self.phone_address_book.id
        })
        self.assertEqual(resp.status_code, 201)
        self.assert_expected_transfer(
            transfer_id=resp.data['id'],
            amount=amount,
            out_address=get_masked_phone(self.phone_address_book.dest_user.username),
            receiver_account=self.dest_account,
            asset=self.usdt,
            account=self.account,
            address_book=self.phone_address_book
        )

    def test_withdraw_with_phone_without_addressbook(self):
        amount = '50'
        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'address': '09123456789',
            'coin': 'USDT',
            'source': 'internal_account',
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'address': '09123456780',
            'coin': 'USDT',
            'source': 'internal_account',
            'code': generate_otp_code(self.user, 'withdraw')
        })
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post('/api/v1/withdraw/', {
            'amount': amount,
            'address': '09123456789',
            'coin': 'USDT',
            'source': 'internal_account',
            'code': generate_otp_code(self.user, 'withdraw')
        })
        self.assertEqual(resp.status_code, 201)
        self.assert_expected_transfer(
            transfer_id=resp.data['id'],
            amount=amount,
            out_address=get_masked_phone(self.dest_user.username),
            receiver_account=self.dest_account,
            asset=self.usdt,
            account=self.account
        )
