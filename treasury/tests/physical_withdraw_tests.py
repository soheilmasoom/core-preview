from decimal import Decimal

from django.test import TestCase, Client

from accounts.models import Account, SystemConfig
from ledger.models import Asset, BalanceLock, Trx
from ledger.utils.test import new_account
from treasury.models import PhysicalWithdraw, PhysicalWithdrawStatus


class PhysicalWithdrawTestCase(TestCase):
    @staticmethod
    def airdrop(asset, account, value):
        asset.get_wallet(account).airdrop(value)

    def assertWithdrawalCreated(self, response, expected_asset, expected_amount, expected_fee):
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data['amount']), Decimal(expected_amount))
        self.assertEqual(Decimal(response.data['fee_amount']), Decimal(expected_fee))
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

        # Setup system config with 3% fee
        config = SystemConfig.get_system_config()
        config.physical_withdraw_fee_percentage = Decimal('3')
        config.save()

    def test_create_xau_withdrawal_with_fee(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))
        data = {
            'asset': 'XAU',
            'amount': '5'
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)

        # Fee is 3% of 5 = 0.15, total = 5.15
        self.assertWithdrawalCreated(response, 'XAU', '5', '0.15')
        self.assertBalanceLocked('5.15')  # Total locked amount
        self.assertWalletBalance(self.xau, self.account, '18.3713')  # 23.5213 - 5.15

    def test_create_xaum_withdrawal_with_fee(self):
        self.airdrop(self.xaum, self.account, Decimal('23521.3'))
        data = {
            'asset': 'XAUM',
            'amount': '10000'
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)

        # Fee is 3% of 10000 = 300, total = 10300
        self.assertWithdrawalCreated(response, 'XAUM', '10000', '300')
        self.assertBalanceLocked('10300')
        self.assertWalletBalance(self.xaum, self.account, '13221.3')  # 23521.3 - 10300

    def test_insufficient_balance_with_fee(self):
        # User has 5g but needs 5.15g (5g + 3% fee)
        self.airdrop(self.xau, self.account, Decimal('5'))

        data = {
            'asset': 'XAU',
            'amount': '5'
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'موجودی کافی نیست')
        self.assertEqual(BalanceLock.objects.count(), 0)
        self.assertWalletBalance(self.xau, self.account, '5')

    def test_invalid_amount_not_multiple_of_five(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))

        data = {
            'asset': 'XAU',
            'amount': '3'  # Not multiple of 5
        }
        response = self.client.post('/api/v1/treasury/withdraw/', data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('مضربی از 5', response.data['error'])
        self.assertEqual(BalanceLock.objects.count(), 0)
        self.assertWalletBalance(self.xau, self.account, '23.5213')

    def test_valid_multiples_of_five(self):
        self.airdrop(self.xau, self.account, Decimal('100'))

        for amount in [5, 10, 15, 20]:
            data = {
                'asset': 'XAU',
                'amount': str(amount)
            }
            response = self.client.post('/api/v1/treasury/withdraw/', data)
            self.assertEqual(response.status_code, 201)

    def test_withdrawal_complete_flow_with_fee(self):
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
        self.assertWalletBalance(self.xau, self.account, '18.3713')

        # Check that the transaction transferred the total amount (5 + 0.15)
        trx = Trx.objects.last()
        self.assertEqual(trx.scope, Trx.TRANSFER)
        self.assertEqual(trx.sender, self.xau.get_wallet(self.account))
        self.assertEqual(trx.receiver, self.xau.get_wallet(Account.out()))
        self.assertEqual(trx.amount, Decimal('5.15'))  # Total with fee

    def test_preview_endpoint(self):
        data = {
            'asset': 'XAU',
            'amount': '10'
        }
        response = self.client.post('/api/v1/treasury/withdraw/preview/', data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['amount']), Decimal('10'))
        self.assertEqual(Decimal(response.data['fee_percentage']), Decimal('3'))
        self.assertEqual(Decimal(response.data['fee_amount']), Decimal('0.3'))
        self.assertEqual(Decimal(response.data['total_amount']), Decimal('10.3'))

    def test_preview_endpoint_not_multiple_of_five(self):
        data = {
            'asset': 'XAU',
            'amount': '7'  # Not multiple of 5
        }
        response = self.client.post('/api/v1/treasury/withdraw/preview/', data)

        self.assertEqual(response.status_code, 400)
        self.assertIn('مضربی از 5', response.data['error'])

    def test_init_endpoint_returns_fee_percentage(self):
        response = self.client.get('/api/v1/treasury/withdraw/init/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('physical_withdraw_fee_percentage', response.data)
        self.assertEqual(Decimal(response.data['physical_withdraw_fee_percentage']), Decimal('3'))

    def test_withdrawal_reject_flow_releases_full_amount(self):
        self.airdrop(self.xau, self.account, Decimal('23.5213'))
        response = self.client.post('/api/v1/treasury/withdraw/', {
            'asset': 'XAU',
            'amount': '5'
        })

        withdraw = PhysicalWithdraw.objects.get(id=response.data['id'])
        initial_lock_id = withdraw.lock_id

        withdraw.reject()

        self.assertWithdrawalStatus(withdraw.id, PhysicalWithdrawStatus.REJECTED)
        self.assertTrue(BalanceLock.objects.filter(key=initial_lock_id).exists())
        # Full balance should be restored
        self.assertWalletBalance(self.xau, self.account, '23.5213')