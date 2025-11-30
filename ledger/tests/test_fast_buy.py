from unittest import mock

from django.test import Client
from django.test import TestCase

from accounts.models import Account
from ledger.models import Asset
from ledger.utils.fields import DONE
from ledger.utils.test import new_account, set_price, new_bankcard, new_zibal_gateway
from ledger.utils.wallet_pipeline import WalletPipeline


def mocked__verify(payment):
    with WalletPipeline() as pipeline:
        payment.accept(pipeline, 1)


class FastBuyTestCase(TestCase):
    def setUp(self) -> None:
        self.account = new_account()
        self.user = self.account.user
        self.client = Client()
        self.bankcard = new_bankcard(user=self.user)
        self.client.force_login(self.user)
        self.usdt = Asset.get(Asset.USDT)
        self.btc = Asset.get('BTC')

        set_price(self.usdt, 1)  # IRT
        set_price(self.btc, 1000)  # USDT

        self.wallet_usdt = self.usdt.get_wallet(self.account)
        self.wallet_btc = self.btc.get_wallet(self.account)

        self.system_wallet_usdt = self.usdt.get_wallet(Account.system())
        self.system_wallet_btc = self.btc.get_wallet(Account.system())
        self.gateway = new_zibal_gateway()

    @mock.patch('financial.models.zibal_gateway.ZibalGateway._verify', side_effect=mocked__verify)
    def test_payment_generate_link(self, *args, **kwargs):
        self.wallet_usdt.airdrop(100)
        resp = self.client.post('/api/v1/fast_buy/', {
            'coin': 'BTC',
            'amount': 1000000,
            'bank_card_id': self.bankcard.id

        })
        self.assertEqual(resp.status_code, 201)
        track_id = resp.json()['callback'].split('/')[-1]
        # print(financial.models.zibal_gateway.ZibalGateway._verify())
        resp_2 = self.client.get('/api/v1/finance/payment/callback/zibal/?trackId={}&success=1&status=2&orderId=1'.format(track_id))
        self.wallet_btc.refresh_from_db()

        self.assertGreater(self.wallet_btc.balance, 950)
