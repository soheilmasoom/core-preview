import json

from django.test import TestCase

from accounts.models import VerificationCode


class AuthTests(TestCase):

    def setUp(self):
        pass

    def test_signup(self):
        phone = '09123456789'
        resp = self.client.post('/api/v1/accounts/signup/init/', {
            'phone': phone
        })
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post('/api/v1/accounts/otp/verify/', {
            'phone': phone,
            'scope': VerificationCode.SCOPE_VERIFY_PHONE,
            'code': '1111'
        })
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post('/api/v1/accounts/signup/', {
            'token': resp.data['token'],
            'password': 'abcefD23!',
            'code': '1111',
            'utm': json.dumps({
                'utm_source': 'google',
                'utm_medium': 'google',
                'gps_adid': 'test',
                'profile_id': '12455',
            })
        })
        self.assertEqual(resp.status_code, 201)
