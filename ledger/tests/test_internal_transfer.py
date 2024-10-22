from datetime import timedelta
from django.test import TestCase, Client
from rest_framework import status
from decimal import Decimal

from accounts.models import User, Account
from ledger.models import Asset, Transfer, Network, NetworkAsset, DepositAddress
from ledger.fields import WithdrawSources
from ledger.models.address_key import AddressKey
from ledger.tasks import update_withdraws
from ledger.utils.test import new_account, set_price, generate_otp_code


class WithdrawViewWithCeleryTestCase(TestCase):
    def setUp(self):
        self.account1 = new_account()
        self.user1 = self.account1.user
        self.user1.level = User.LEVEL2
        self.user1.custom_crypto_withdraw_ceil = 1000000000
        self.user1.save()

        self.account2 = new_account()
        self.user2 = self.account2.user
        self.user2.phone = "09121231234"
        self.user2.level = User.LEVEL2
        self.user2.custom_crypto_withdraw_ceil = 1000000000
        self.user2.save()

        self.client = Client()
        self.client.force_login(self.user1)

        self.btc, _ = Asset.objects.get_or_create(symbol='BTC', defaults={
            'name': 'Bitcoin', 'name_fa': 'بیت‌کوین', 'enable': True
        })
        self.usdt, _ = Asset.objects.get_or_create(symbol='USDT', defaults={
            'name': 'Tether', 'name_fa': 'تتر', 'enable': True
        })
        self.irt, _ = Asset.objects.get_or_create(symbol='IRT', defaults={
            'name': 'Rial', 'name_fa': 'ریال', 'enable': True
        })

        set_price(self.btc, 30000)
        set_price(self.usdt, 30000)

        self.wallet_btc_user1 = self.btc.get_wallet(self.account1)
        self.wallet_usdt_user1 = self.usdt.get_wallet(self.account1)

        self.wallet_btc_user1.airdrop(Decimal('0.02'))
        self.wallet_usdt_user1.airdrop(Decimal('1000'))

        self.network_btc, _ = Network.objects.get_or_create(symbol='BTC', defaults={
            'name': 'Bitcoin',
            'address_regex': '^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$',
            'deposit_need_memo': False,
            'withdraw_allow_memo': False,
            'can_withdraw': True,
            'memo_title_fa': '',
            'memo_regex': ''
        })

        self.network_asset_btc, _ = NetworkAsset.objects.get_or_create(asset=self.btc, can_withdraw=True, can_deposit=True, network=self.network_btc ,defaults={
                            'withdraw_fee': 0,
                            'withdraw_min': 0,
                            'withdraw_max': 0,
                            'withdraw_precision': 8,
                        })
        self.network_asset_btc.withdraw_enabled = True
        self.network_asset_btc.withdraw_min = Decimal('0.0001')
        self.network_asset_btc.withdraw_max = Decimal('1')
        self.network_asset_btc.withdraw_fee = Decimal('0.00001')
        self.network_asset_btc.withdraw_precision = 8
        self.network_asset_btc.hedger_withdraw_enable = True
        self.network_asset_btc.save()

    def test_internal_transfer_to_another_user_with_processing(self):

        code = generate_otp_code(self.user1, 'withdraw')

        url = '/api/v1/withdraw/'
        data = {
            'source': "internal_account",
            'address': self.user2.phone,
            'coin': 'USDT',
            'amount': '100',
            'description': 'Test transfer',
            'code': code,
            'totp': ''
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transfer.objects.count(), 1)

        transfer = Transfer.objects.first()
        self.assertEqual(transfer.status, 'process')

        transfer.created = transfer.created - timedelta(seconds=2*transfer.FREEZE_SECONDS)
        transfer.save(update_fields=['created'])
        update_withdraws()

        transfer.refresh_from_db()

        self.assertEqual(transfer.status, 'done')

        receiver_wallet = self.usdt.get_wallet(self.account2)
        self.assertEqual(receiver_wallet.balance, Decimal('100'))

    def test_withdraw_to_internal_address_with_processing(self):
        address = '1BoatSLRHtKNngkdXEeobR76b53LETtpyT'
        address_key = AddressKey.objects.create(account=self.account2, address=address)

        deposit_address = DepositAddress.objects.create(
            address=address,
            network=self.network_btc,
            address_key=address_key
        )

        code = generate_otp_code(self.user1, 'withdraw')

        url = '/api/v1/withdraw/'
        data = {
            'coin': 'BTC',
            'network': 'BTC',
            'amount': '0.001',
            'address': deposit_address.address,
            'memo': '',
            'code': code,
            'totp': ''
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transfer.objects.count(), 1)

        transfer = Transfer.objects.first()
        self.assertEqual(transfer.status, 'process')

        transfer.created = transfer.created - timedelta(seconds=2*transfer.FREEZE_SECONDS)
        transfer.save(update_fields=['created'])
        update_withdraws()

        transfer.refresh_from_db()

        self.assertEqual(transfer.status, 'done')

        receiver_wallet = self.btc.get_wallet(self.account2)
        self.assertEqual(receiver_wallet.balance, Decimal('0.001'))

    def test_internal_transfer_insufficient_balance(self):

        code = generate_otp_code(self.user1, 'withdraw')

        url = '/api/v1/withdraw/'
        data = {
            'source': 'internal_account',
            'address': self.user2.phone,
            'coin': 'USDT',
            'amount': '2000',
            'description': 'Test transfer',
            'code': code,
            'totp': ''
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

