import requests
from decouple import config
from django.conf import settings
from django.urls import reverse

from financial.models import Gateway, BankCard, PaymentRequest
from financial.models.gateway import GatewayFailed


class JibimoGateway(Gateway):
    # BASE_URL = 'https://core.paystar.ir/api/pardakht'

    # def create_payment_request(self, bank_card: BankCard, amount: int, source: str) -> PaymentRequest:
        # base_url = config('PAYMENT_PROXY_HOST_URL', default='') or settings.HOST_URL
        #
        # resp = requests.post(
        #     self.BASE_URL + '/create',
        #     headers={
        #         'Authorization': 'Bearer ' + self.merchant_id
        #     },
        #     json={
        #         'amount': amount * 10,
        #         'callback': base_url + reverse('finance:jibimo-callback'),
        #         'card_number': bank_card.card_pan,
        #         'sign': 0
        #     },
        #     timeout=30,
        # )
        #
        # resp_data = resp.json()
        #
        # if not resp.ok or resp_data['status'] != 1:
        #     print('status code', resp.status_code)
        #     print('body', resp_data)
        #
        #     raise GatewayFailed
        #
        # authority = resp.json()['token']
        #
        # return PaymentRequest.objects.create(
        #     bank_card=bank_card,
        #     amount=amount,
        #     gateway=self,
        #     authority=authority,
        #     source=source,
        # )
    #
    # def get_initial_redirect_url(self, payment_request: PaymentRequest) -> str:
    #     payment_proxy = config('PAYMENT_PROXY_HOST_URL', default='')
    #
    #     if not payment_proxy:
    #         return super(PaydotirGateway, self).get_initial_redirect_url(payment_request)
    #     else:
    #         return payment_proxy + '/api/v1/finance/payment/go/?gateway={gateway}&authority={authority}'.format(
    #             gateway=self.PAYIR,
    #             authority=payment_request.authority
    #         )
    #
    # @classmethod
    # def get_payment_url(cls, authority: str):
    #     return 'https://pay.ir/pg/{}'.format(authority)
    #
    # def _verify(self, payment: Payment):
    #     payment_request = payment.paymentrequest
    #
    #     resp = requests.post(
    #         self.BASE_URL + '/pg/verify',
    #         data={
    #             'api': payment_request.gateway.merchant_id,
    #             'token': payment_request.authority
    #         },
    #         timeout=30,
    #     )
    #
    #     data = resp.json()
    #
    #     if data['status'] == 1:
    #         with WalletPipeline() as pipeline:
    #             ref_id = data.get('transId')
    #             payment.accept(pipeline, ref_id)
    #
    #     else:
    #         payment.status = CANCELED
    #         payment.ref_status = data['status']
    #         payment.save()

    class Meta:
        proxy = True
