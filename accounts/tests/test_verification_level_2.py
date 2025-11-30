from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django.test import TestCase, Client
from accounts.tasks import verify_user
from accounts.models import User
from financial.utils.test import new_user


class VerificationLevel2TestCase(TestCase):

    def setUp(self):
        self.user_verify = new_user(name='user_test_2', phone='09125555555')
        self.user = new_user(level=User.LEVEL1)
        self.client = Client()

    def test_success_verify(self):
        self.client.force_login(self.user)

        data = {
            'first_name': 'علی',
            'last_name': 'صالحی',
            'birth_date': '2000-01-01',
            'national_code': '1230046917',
            'card_pan': '6104337574599260',
        }

        resp = self.client.post('/api/v1/accounts/verify/basic/', data)
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get('/api/v1/accounts/verify/basic/')

        for key, value in data.items():
            resp_val = resp.data[key]

            if key == 'card_pan':
                resp_val = resp_val['card_pan']

            self.assertEqual(resp_val, value)

    def test_error_age(self):
        self.client.force_login(self.user)
        resp = self.client.post('/api/v1/accounts/verify/basic/', {
            'first_name': 'علی',
            'last_name': 'صالحی',
            'birth_date': '2200-01-01',
            'national_code': '1230046917',
            'card_pan': '6104337574599260',
        })
        self.assertEqual(resp.status_code, 400)

    def test_erroe_user_verify(self):
        self.client.force_login(self.user_verify)
        resp = self.client.post('/api/v1/accounts/verify/basic/', {
            'first_name': 'علی',
            'last_name': 'صالحی',
            'birth_date': '2000-01-01',
            'national_code': '1230046917',
            'card_pan': '6104337574599260',
        })
        self.assertEqual(resp.status_code, 400)
