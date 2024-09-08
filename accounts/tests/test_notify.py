from uuid import uuid4

from django.contrib.auth.models import Permission
from rest_framework.test import APITestCase, APIClient

from accounts.models import User, SmsNotification, Notification
from financial.utils.test import new_user, new_custom_token


class TestNotify(APITestCase):
    def setUp(self):
        self.user = new_user(name='test_user_1', phone='09305913458', level=User.LEVEL1)
        self.token = new_custom_token(self.user)

        permission = Permission.objects.get(codename='can_generate_notification')

        # Add the permission to the user
        self.user.user_permissions.add(permission)

        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_notify(self):
        group_id = uuid4()

        resp = self.client.post('/api/v1/accounts/notify/', data={
            'user_id': self.user.id,
            'type': 'sms',
            'content': 'Hello there',
            'group_id': str(group_id)

        }, HTTP_AUTHORIZATION=f'Token {self.token}')

        data = resp.data

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(SmsNotification.objects.filter(group_id=group_id, recipient_id=self.user.id))

    def test_bulk_notify(self):
        group_id = uuid4()

        resp = self.client.post('/api/v1/accounts/notify/', [{
            'user_id': self.user.id,
            'type': 'sms',
            'content': 'Hello there',
            'group_id': str(group_id)

        }, {
            'user_id': self.user.id,
            'type': 'push',
            'title': 'hi',
            'content': 'Hello there',
            'group_id': str(group_id)

        }], format='json')

        data = resp.data

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(SmsNotification.objects.filter(group_id=group_id, recipient_id=self.user.id))
        self.assertTrue(Notification.objects.filter(group_id=group_id, recipient_id=self.user.id))
