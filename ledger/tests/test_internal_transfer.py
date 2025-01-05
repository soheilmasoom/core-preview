from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, Client
from rest_framework import status

from accounts.models import User
from accounts.utils.test import new_user
from ledger.fields import WithdrawSources
from ledger.models import Asset, Transfer
from ledger.models.trx import Trx
from ledger.tasks import update_withdraws
from ledger.tasks.withdraw import process_internal_transfers
from ledger.utils.fields import PROCESS
from ledger.utils.test import set_price, generate_otp_code, new_network_asset, new_network, new_account, \
    new_deposit_address


class InternalTransferTestCase(TestCase):
    def setUp(self):
        self.user1 = new_user(level=User.LEVEL3)
        self.account1 = self.user1.get_account()

        self.user2 = new_user(level=User.LEVEL3, phone='09121231234')
        self.account2 = self.user2.get_account()

        self.client = Client()
        self.client.force_login(self.user1)

        self.btc = Asset.get('BTC')
        self.usdt = Asset.get('USDT')

        set_price(self.btc, 30000)
        set_price(self.usdt, 30000)

        self.wallet_btc_user1 = self.btc.get_wallet(self.user1.get_account())
        self.wallet_usdt_user1 = self.usdt.get_wallet(self.user1.get_account())

        self.wallet_btc_user1.airdrop(Decimal('0.02'))
        self.wallet_usdt_user1.airdrop(Decimal('1000'))

        self.btc_network = new_network(symbol='BTC')
        new_network_asset(asset=self.btc, network=self.btc_network)

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
        deposit_address = new_deposit_address(account=self.account2, network=self.btc_network, address=address)

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

    def test_withdraw_to_internal_address_with_processing2(self):
        address = '1BoatSLRHtKNngkdXEeobR76b53LETtpyT'
        deposit_address = new_deposit_address(account=self.account2, network=self.btc_network, address=address)

        code = generate_otp_code(self.user1, 'withdraw')

        response = self.client.post('/api/v1/withdraw/', {
            'coin': 'BTC',
            'network': 'BTC',
            'amount': '0.001',
            'address': deposit_address.address,
            'memo': '',
            'code': code,
            'totp': ''
        })
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

        self.assertEqual(
            Trx.objects.get(sender=self.btc.get_wallet(self.account1)).group_id,
            Transfer.objects.get(receiver_account=receiver_wallet.account).group_id)

    def test_withdraw_to_memo_internal(self):
        xrp = Asset.get('XRP')
        xrp_network = new_network(symbol='XRP')
        xrp_network.deposit_need_memo = True
        xrp_network.withdraw_allow_memo = True
        xrp_network.save()

        new_network_asset(xrp, xrp_network)

        account3 = new_account()
        address = 'rhubarbMVC2nzASf3qSGQcUKtLnAzqcBjp'

        new_deposit_address(account=self.account1, network=xrp_network, address=address, memo='1')
        new_deposit_address(account=account3, network=xrp_network, address=address, memo='3')
        new_deposit_address(account=self.account2, network=xrp_network, address=address, memo='2')

        wallet1 = xrp.get_wallet(self.account1)

        wallet1.airdrop(100)

        set_price(xrp, 5)

        code = generate_otp_code(self.user1, 'withdraw')
        response = self.client.post('/api/v1/withdraw/', {
            'coin': 'XRP',
            'network': 'XRP',
            'amount': '10',
            'address': address,
            'memo': '2',
            'code': code,
            'totp': ''
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Transfer.objects.count(), 1)

        transfer = Transfer.objects.last()
        self.assertEqual(transfer.source, WithdrawSources.INTERNAL)

        process_internal_transfers()
        self.assertEqual(Transfer.objects.filter(status=PROCESS).count(), 1)

        transfer.created -= timedelta(seconds=Transfer.FREEZE_SECONDS)
        transfer.save()

        process_internal_transfers()
        self.assertEqual(Transfer.objects.filter(status=PROCESS).count(), 0)

        wallet1.refresh_from_db()
        wallet2 = xrp.get_wallet(self.account2)
        wallet3 = xrp.get_wallet(account3)

        self.assertEqual(wallet1.balance, 90)
        self.assertEqual(wallet2.balance, 10)
        self.assertEqual(wallet3.balance, 0)
