from django.test import Client
from django.test import TestCase

from accounts.models import User
from financial.models import Payment
from financial.models.direct_debit_connection import DirectDebitConnection
from financial.models.direct_debit_request import DirectDebitRequest
from ledger.utils.test import new_account
from financial.utils.test import new_direct_debit_bank, new_direct_debit_gateway


class DirectDebitTestCase(TestCase):

    def setUp(self):
        self.account = new_account()
        self.user = self.account.user
        self.user.level = User.LEVEL4
        self.user.save(update_fields=['level'])
        self.client = Client()
        self.client.force_login(self.user)
        self.gateway = new_direct_debit_gateway()
        self.bank_slug = 'POST'
        self.direct_debit_bank = new_direct_debit_bank(self.bank_slug, self.gateway)
        self.bank_id = self.direct_debit_bank.id

    def test_get_banks_list(self):
        resp = self.client.get('/api/v1/finance/direct-debit/banks/',)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()[0]['info']['slug'], self.bank_slug)

    def test_get_authorization_url(self):
        resp = self.client.post('/api/v1/finance/direct-debit/connect/POST/', )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['url'], "https://subscription.vandar.io/authorizations/test_token")
        self.assertEqual(DirectDebitConnection.objects.all().count(), 1)

    def test_accept_authorization_id(self):
        self.test_get_authorization_url()
        resp = self.client.get('/api/v1/finance/direct-debit/callback/vandar/', {
            'token': 'test_token',
            'status': 'SUCCEED',
            'authorization_id': '123456789'
        })
        self.assertEqual(resp.status_code, 302)
        auth = DirectDebitConnection.objects.filter(token='test_token')
        self.assertEqual(auth.count(), 1)
        self.assertEqual(auth[0].verified, True)
        self.assertEqual(auth[0].auth_id, '123456789')

    def test_direct_debit_charge(self):
        self.test_accept_authorization_id()
        resp = self.client.post('/api/v1/finance/direct-debit/charge/POST/', {
            'amount': 5000,
        }, content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        direct_debit_request = DirectDebitRequest.objects.all().first()
        self.assertEqual(direct_debit_request.amount, 5000)
        payment = Payment.objects.filter(source=Payment.DIRECT_DEBIT).first()
        self.assertEqual(payment.amount, 5000)
