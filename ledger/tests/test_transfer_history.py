from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from django.contrib.auth import get_user_model
from ledger.utils.test import new_account
from django.test import Client

from accounts.models import Account
from ledger.models import Asset, Transfer
from ledger.utils.fields import DONE, INIT
from ledger.utils.test import generate_otp_code, set_price

User = get_user_model()

class WithdrawHistoryViewTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='1', password='2')
        self.client.force_authenticate(user=self.user)

        self.account = Account.objects.create(user=self.user)

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

    def test_withdraw_history_filter_by_status(self):
        code = generate_otp_code(self.user1, 'withdraw')

        url = '/api/v1/withdraw/'
        data = {
            'source': "internal_account",
            'address': self.user2.phone,
            'coin': 'USDT',
            'amount': '1',
            'description': 'Test transfer',
            'code': code,
            'totp': ''
        }
        transfer_response = self.client.post(url, data)

        response = self.client.get('/api/v1/withdraw/list/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        transfer_data = response.data['results'][0]
        self.assertEqual(transfer_data['id'], transfer_response.json()['id'])

        response = self.client.get('/api/v1/withdraw/list/', {'status': INIT})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_withdraw_history_no_transfers(self):
        Transfer.objects.all().delete()
        response = self.client.get('/api/v1/withdraw/list/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_withdraw_history_status_code(self):
        response = self.client.get('/api/v1/withdraw/list/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
