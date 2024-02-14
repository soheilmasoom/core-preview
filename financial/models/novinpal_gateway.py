import requests
from django.urls import reverse

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed
from ledger.utils.fields import CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline


class NovinpalGateway(Gateway):
    BASE_URL = 'https://gw.novinpal.ir'
    REDIRECT_BASE_URL = 'https://api.raastin.website'

    def create_payment_request(self, bank_card: BankCard, amount: int, source: str) -> PaymentRequest:
        fee = self.get_ipg_fee(amount)

        payment_request = PaymentRequest.objects.create(
            bank_card=bank_card,
            amount=amount - fee,
            fee=fee,
            gateway=self,
            source=source,
        )

        rial_amount = amount * 10

        order_id = str(payment_request.id)
        callback_url = self.REDIRECT_BASE_URL + reverse('finance:novinpal-callback') + f'?id={payment_request.id}'

        resp = requests.post(
            self.BASE_URL + '/invoice/request',
            data={
                'api_key': self.deposit_api_key,
                'amount': rial_amount,
                'return_url': callback_url,
                'order_id': order_id,
                'card_number': bank_card.card_pan,
            },
            timeout=30,
        )

        resp_data = resp.json()

        if not resp.ok or resp_data['status'] != 1:
            print('status code', resp.status_code)
            print('body', resp_data)

            raise GatewayFailed

        payment_request.authority = resp_data['refId']
        payment_request.save(update_fields=['authority'])

        return payment_request

    @classmethod
    def get_payment_url(cls, payment_request: PaymentRequest):
        return f'{cls.BASE_URL}/invoice/start/{payment_request.authority}'

    def _verify(self, payment: Payment, **kwargs):
        payment_request = payment.paymentrequest

        resp = requests.post(
            self.BASE_URL + '/invoice/verify',
            data={
                'api_key': self.deposit_api_key,
                'ref_id': payment_request.authority
            },
            timeout=30,
        )

        data = resp.json()

        if int(data['status']) == 1:
            with WalletPipeline() as pipeline:
                payment.accept(pipeline, payment.ref_id)

        else:
            payment.status = CANCELED
            payment.ref_status = data['status']
            payment.save()

    class Meta:
        proxy = True
