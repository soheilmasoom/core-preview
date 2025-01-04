from decimal import Decimal

from django.test import TestCase, Client

from accounts.models import Account
from ledger.models import Asset, BalanceLock, Trx
from ledger.utils.test import new_account
from treasury.models import PhysicalWithdraw, PhysicalWithdrawStatus


class PhysicalWithdrawTestCase(TestCase):
    @staticmethod
    def airdrop(asset, account, value):
        asset.get_wallet(account).airdrop(value)

    def assertWithdrawalCreated(self, response, expected_asset, expected_amount):
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['amount'], f"{Decimal(expected_amount):.3f}")
        self.assertEqual(response.data['asset'], expected_asset)

    def assertBalanceLocked(self, expected_amount):
        bl = BalanceLock.objects.first()
        self.assertIsNotNone(bl)
        self.assertEqual(bl.amount, Decimal(expected_amount))

    def assertWalletBalance(self, asset, account, expected_balance):
        balance = asset.get_wallet(account).get_free()
        self.assertEqual(balance, Decimal(expected_balance))

    def assertWithdrawalStatus(self, withdraw_id, expected_status):
        withdraw = PhysicalWithdraw.objects.get(id=withdraw_id)
        self.assertEqual(withdraw.status, expected_status)

    def setUp(self):
        self.xau = Asset.objects.create(name='XAU', symbol='XAU', enable=True)
        self.xag = Asset.objects.create(name='XAG', symbol='XAG', enable=True)
        self.xaum = Asset.objects.create(name='XAUM', symbol='XAUM', enable=True)
        self.account = new_account()
        self.client = Client()
        self.client.force_login(self.account.user)

    def test_create_xau_withdrawal(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))
        data = {
            'asset': 'XAU',
            'amount': '5'
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)
        self.assertWithdrawalCreated(response, 'XAU', '5')
        self.assertBalanceLocked('5')
        self.assertWalletBalance(self.xau, self.account, '18.5213')

    def test_create_xaum_withdrawal(self):
        self.airdrop(self.xaum, self.account, Decimal('23521.3'))
        data = {
            'asset': 'XAUM',
            'amount': '10'
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)
        self.assertWithdrawalCreated(response, 'XAUM', '10000')
        self.assertBalanceLocked('10000')
        self.assertWalletBalance(self.xaum, self.account, '13521.3')

    def test_insufficient_balance_xau_withdrawal(self):
        self.airdrop(self.xau, self.account, Decimal('3'))

        data = {
            'asset': 'XAU',
            'amount': '5'
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'موجودی کافی نیست')
        self.assertEqual(BalanceLock.objects.count(), 0)
        self.assertWalletBalance(self.xau, self.account, '3')

    def test_invalid_amount_not_multiple_of_five(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))

        data = {
            'asset': 'XAU',
            'amount': '3'  # Not multiple of 5
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BalanceLock.objects.count(), 0)
        self.assertWalletBalance(self.xau, self.account, '23.5213')

    def test_withdrawal_approve_flow(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))
        response = self.client.post('/api/v1/treasury/withdraw/', {
            'asset': 'XAU',
            'amount': '5'
        })

        withdraw = PhysicalWithdraw.objects.get(id=response.data['id'])
        initial_lock_id = withdraw.lock_id

        # Approve the withdrawal
        withdraw.approve()

        # Verify status and lock still exists
        self.assertWithdrawalStatus(withdraw.id, PhysicalWithdrawStatus.APPROVED)
        self.assertTrue(BalanceLock.objects.filter(key=initial_lock_id).exists())
        self.assertWalletBalance(self.xau, self.account, '18.5213')

    def test_withdrawal_reject_flow(self):
        # Create initial withdrawal
        self.airdrop(self.xau, self.account, Decimal('23.5213'))
        response = self.client.post('/api/v1/treasury/withdraw/', {
            'asset': 'XAU',
            'amount': '5'
        })

        withdraw = PhysicalWithdraw.objects.get(id=response.data['id'])
        initial_lock_id = withdraw.lock_id

        withdraw.reject()

        self.assertWithdrawalStatus(withdraw.id, PhysicalWithdrawStatus.REJECTED)
        self.assertFalse(BalanceLock.objects.filter(key=initial_lock_id).exists())
        self.assertWalletBalance(self.xau, self.account, '23.5213')

    def test_withdrawal_complete_flow(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))
        self.client.post('/api/v1/treasury/withdraw/', {
            'asset': 'XAU',
            'amount': '5'
        })

        withdraw = PhysicalWithdraw.objects.latest('created_at')
        initial_lock_id = withdraw.lock_id

        withdraw.approve()

        withdraw.complete()

        self.assertWithdrawalStatus(withdraw.id, PhysicalWithdrawStatus.COMPLETED)
        self.assertTrue(BalanceLock.objects.filter(key=initial_lock_id).exists())
        self.assertWalletBalance(self.xau, self.account, '18.5213')
        trx = Trx.objects.last()
        self.assertEqual(trx.scope, Trx.TRANSFER)
        self.assertEqual(trx.sender, self.xau.get_wallet(self.account))
        self.assertEqual(trx.receiver, self.xau.get_wallet(Account.out()))
        self.assertEqual(trx.amount, Decimal('5'))
