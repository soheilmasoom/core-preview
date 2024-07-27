import requests
from django.conf import settings
from django.urls import reverse
from decouple import config

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed
from ledger.utils.fields import DONE, CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline


class PaydotirGateway(Gateway):
    BASE_URL = 'https://pay.ir'

    def create_payment_request(self, bank_card: BankCard, amount: int, source: str) -> PaymentRequest:
        base_url = config('PAYMENT_PROXY_HOST_URL', default='') or settings.HOST_URL

        resp = requests.post(
            self.BASE_URL + '/pg/send',
            json={
                'api': self.merchant_id,
                'amount': amount * 10,
                'description': 'افزایش اعتبار',
                'redirect': base_url + reverse('finance:paydotir-callback'),
                'validCardNumber': bank_card.card_pan
            },
            timeout=30,
        )

        resp_data = resp.json()

        if not resp.ok or resp_data['status'] != 1:
            print('status code', resp.status_code)
            print('body', resp_data)

            raise GatewayFailed

        authority = resp.json()['token']

        return PaymentRequest.objects.create(
            bank_card=bank_card,
            amount=amount,
            gateway=self,
            authority=authority,
            source=source,
        )

    def get_initial_redirect_url(self, payment_request: PaymentRequest) -> str:
        payment_proxy = config('PAYMENT_PROXY_HOST_URL', default='')

        if not payment_proxy:
            return super(PaydotirGateway, self).get_initial_redirect_url(payment_request)
        else:
            return payment_proxy + '/api/v1/finance/payment/go/?gateway={gateway}&authority={authority}'.format(
                gateway=self.PAYIR,
                authority=payment_request.authority
            )

    @classmethod
    def get_payment_url(cls, payment_request: PaymentRequest):
        return 'https://pay.ir/pg/{}'.format(payment_request.authority)

    def _verify(self, payment: Payment):
        payment_request = payment.paymentrequest

        resp = requests.post(
            self.BASE_URL + '/pg/verify',
            data={
                'api': payment_request.gateway.merchant_id,
                'token': payment_request.authority
            },
            timeout=30,
        )

        data = resp.json()

        if data['status'] == 1:
            with WalletPipeline() as pipeline:
                ref_id = data.get('transId')
                payment.accept(pipeline, ref_id)

        else:
            payment.status = CANCELED
            payment.ref_status = data['status']
            payment.save()

    class Meta:
        proxy = True
