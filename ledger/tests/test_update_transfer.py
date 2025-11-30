from rest_framework.test import APIClient

from ledger.utils.test import new_account, new_network, set_up_user
from ledger.models import Transfer


class DepositTransferUpdateTestCase:
    def __init__(self):
        self.client = APIClient()
        self.user = set_up_user()
        self.client.force_authenticate(self.user)

    def test1(self):
        data = {

        }
        res = self.client.post('')

        return self.assertEqual(res.status_code, 200)


class WithdrawTransferUpdateTestCase:
    def __init__(self):
        self.client = APIClient()
        self.user = set_up_user()
        self.client.force_authenticate(self.user)

    def test1(self):
        transfer = Transfer.objects.create()
        data = {

        }
        res = self.client.post('')
        return self.assertEqual(res.status_code, 200)