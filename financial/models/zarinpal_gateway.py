import requests
from django.conf import settings
from django.urls import reverse

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed, logger
from ledger.utils.fields import DONE, CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline


class ZarinpalGateway(Gateway):
    BASE_URL = 'https://api.zarinpal.com'

    def create_payment_request(self, bank_card: BankCard, amount: int, source: str) -> PaymentRequest:
        resp = requests.post(
            self.BASE_URL + '/pg/v4/payment/request.json',
            json={
                'merchant_id': self.merchant_id,
                'amount': amount,
                'currency': 'IRT',
                'description': 'افزایش اعتبار',
                'callback_url': settings.HOST_URL + reverse('finance:zarinpal-callback'),
                'metadata': {"card_pan":  bank_card.card_pan}
            },
            timeout=30,
        )

        if not resp.ok or resp.json()['data']['code'] != 100:
            raise GatewayFailed

        authority = resp.json()['data']['authority']
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
        return 'https://www.zarinpal.com/pg/StartPay/{}'.format(payment_request.authority)

    def _verify(self, payment: Payment):
        payment_request = payment.paymentrequest

        resp = requests.post(
            self.BASE_URL + '/pg/v4/payment/verify.json',
            data={
                'merchant_id': payment_request.gateway.merchant_id,
                'amount': payment_request.amount,
                'authority': payment_request.authority
            },
            timeout=30,
        )

        data = resp.json()['data']

        if data['code'] == 101:
            logger.warning('duplicate verify!', extra={'payment_id': payment.id})

        if data['code'] in (100, 101):
            with WalletPipeline() as pipeline:
                ref_id = data.get('ref_id')

                payment.accept(pipeline, ref_id)

        else:
            payment.status = CANCELED
            payment.ref_status = data['code']
            payment.save()

    class Meta:
        proxy = True