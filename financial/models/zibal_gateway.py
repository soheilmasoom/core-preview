import logging

import requests
from django.conf import settings
from django.urls import reverse

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed
from ledger.utils.fields import DONE, CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)


class ZibalGateway(Gateway):
    BASE_URL = 'https://gateway.zibal.ir'

    def create_payment_request(self, bank_card: BankCard, amount: int, source: str) -> PaymentRequest:
        callback_host = self.ipg_callback_host or settings.HOST_URL

        resp = requests.post(
            self.BASE_URL + '/v1/request',
            json={
                'merchant': self.merchant_id,
                'amount': amount * 10,
                'callbackUrl': callback_host + reverse('finance:zibal-callback'),
                'description': 'افزایش اعتبار',
                'allowedCards': bank_card.card_pan
            },
            timeout=30,
        )

        if resp.json()['result'] != 100:
            logger.info('zibal gateway connection error %s' % resp.json())
            raise GatewayFailed

        authority = resp.json()['trackId']
        fee = self.get_ipg_fee(amount)

        return PaymentRequest.objects.create(
            bank_card=bank_card,
            amount=amount - fee,
            fee=fee,
            gateway=self,
            authority=authority,
            source=source,
        )

    @classmethod
    def get_payment_url(cls, payment_request: PaymentRequest):
        return 'https://gateway.zibal.ir/start/{}'.format(payment_request.authority)

    def _verify(self, payment: Payment, **kwargs):
        payment_request = payment.paymentrequest

        resp = requests.post(
            self.BASE_URL + '/v1/verify',
            json={
                'merchant': payment_request.gateway.merchant_id,
                'trackId': int(payment_request.authority)
            },
            timeout=30,
        )

        data = resp.json()
        print('verify %s' % payment)
        print(data)

        if data['result'] in (100, 201):
            with WalletPipeline() as pipeline:
                ref_id = data.get('refNumber', 0)

                payment.accept(pipeline, ref_id)

        else:
            payment.status = CANCELED
            payment.ref_status = data.get('status', 0)
            payment.save()

    class Meta:
        proxy = True
