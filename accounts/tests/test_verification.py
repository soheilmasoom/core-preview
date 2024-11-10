from django.test import TestCase, Client, override_settings, RequestFactory

from accounts.models import VerificationCode
from accounts.utils.test import new_user, new_phone


class VerificationTests(TestCase):

    def setUp(self):
        self.user = new_user(phone='09305913458')

        self.auth_client = Client()
        self.auth_client.force_login(self.user)

        self.factory = RequestFactory()

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

    @override_settings(GENERATE_FAKE_OTP=False)
    def test_otp_randomness(self):
        request = self.factory.get('/', REMOTE_ADDR='127.0.0.1')

        codes = []

        for i in range(10):
            code = VerificationCode.send_otp_code(request, phone=new_phone(), scope=VerificationCode.SCOPE_VERIFY_PHONE)
            codes.append(code.code)
            self.assertGreaterEqual(code.code, 1e3)
            self.assertLess(code.code, 1e4)

        self.assertGreater(len(set(codes)), 5)

        codes = []

        for i in range(10):
            code = VerificationCode.send_otp_code(
                request=request,
                phone=new_phone(),
                user=self.user,
                scope=VerificationCode.SCOPE_CRYPTO_WITHDRAW
            )
            codes.append(code.code)
            self.assertGreaterEqual(code.code, 1e5)
            self.assertLess(code.code, 1e6)

        self.assertGreater(len(set(codes)), 5)
