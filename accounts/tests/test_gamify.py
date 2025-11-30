from django.test import TestCase, Client

from accounts.models import User
from financial.utils.test import new_user


class Gamification(TestCase):

    def setUp(self):
        self.user_1 = new_user(name='test_user_1', phone='09305913458', level=User.LEVEL1)
        self.client = Client()
        self.client.force_login(self.user_1)

    def test_get_goals(self):
        resp = self.client.get('/api/v1/gamify/missions/')
        self.assertEqual(resp.status_code, 200)
