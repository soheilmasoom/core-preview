import json
import time

from django.test import TestCase, Client

from accounts.models import VerificationCode
from accounts.utils.test import new_user


class VerificationTests(TestCase):

    def setUp(self):
        self.user = new_user(phone='09305913458')

        self.auth_client = Client()
        self.auth_client.force_login(self.user)

    def test_send_otp(self):
        resp = self.auth_client.post('/api/v1/accounts/otp/send/', {
            'scope': 'withdraw'
        })

        self.assertEqual(resp.status_code, 201)

        resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
            'scope': 'withdraw',
            'phone': self.user.phone,
            'code': '111112'
        })

        self.assertEqual(resp.status_code, 400)

        resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
            'scope': 'fiat_withdraw',
            'phone': self.user.phone,
            'code': '111111'
        })

        self.assertEqual(resp.status_code, 400)

        resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
            'scope': 'withdraw',
            'phone': '09123456789',
            'code': '111111'
        })

        self.assertEqual(resp.status_code, 400)

        resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
            'scope': 'withdraw',
            'phone': self.user.phone,
            'code': '111111'
        })

        self.assertEqual(resp.status_code, 201)

        resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
            'scope': 'withdraw',
            'phone': self.user.phone,
            'code': '111111'
        })

        self.assertEqual(resp.status_code, 400)

    def test_missed_otp(self):
        resp = self.auth_client.post('/api/v1/accounts/otp/send/', {
            'scope': 'withdraw'
        })

        self.assertEqual(resp.status_code, 201)

        for i in range(10):
            resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
                'scope': 'withdraw',
                'phone': self.user.phone,
                'code': f'222{i}'
            })
            self.assertEqual(resp.status_code, 400)

        resp = self.auth_client.post('/api/v1/accounts/otp/verify/', {
            'scope': 'withdraw',
            'phone': self.user.phone,
            'code': '111111'
        })

        self.assertEqual(resp.status_code, 400)

    def test_otp_randomness(self):
        pass
