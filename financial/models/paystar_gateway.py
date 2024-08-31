import hashlib
import hmac

import requests
from django.conf import settings
from django.urls import reverse

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed
from ledger.utils.fields import CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline


class PaystarGateway(Gateway):
    BASE_URL = 'https://core.paystar.ir/api/pardakht'

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
        callback_url = settings.HOST_URL + reverse('finance:paystar-callback') + f'?id={payment_request.id}'

        sign_message = f'{rial_amount}#{order_id}#{callback_url}'
        sign = hmac.new(self.deposit_api_secret.encode(), sign_message.encode(), hashlib.sha512).hexdigest()

        resp = requests.post(
            self.BASE_URL + '/create',
            headers={
                'Authorization': 'Bearer ' + self.merchant_id
            },
            data={
                'amount': rial_amount,
                'callback': callback_url,
                'order_id': order_id,
                'card_number': bank_card.card_pan,
                'sign': sign,
                'callback_method': 1
            },
            timeout=30,
        )

        resp_data = resp.json()

        if not resp.ok or resp_data['status'] != 1:
            payment_request.details += f'status code: {resp.status_code}\n'
            payment_request.details += f'body: {resp_data}'
            payment_request.save(update_fields=['details'])

            raise GatewayFailed

        data = resp_data['data']

        payment_request.authority = data['ref_num']
        payment_request.token = data['token']
        payment_request.save(update_fields=['authority', 'token'])

        return payment_request

    @classmethod
    def get_payment_url(cls, payment_request: PaymentRequest):
        return f'https://core.paystar.ir/api/pardakht/payment?token={payment_request.token}'

    def _verify(self, payment: Payment):
        payment_request = payment.paymentrequest
        card_number = payment.card_pan

        amount = payment_request.rial_amount
        ref_num = payment_request.authority

        sign_message = f'{amount}#{ref_num}#{card_number}#{payment.ref_id}'
        sign = hmac.new(self.deposit_api_secret.encode(), sign_message.encode(), hashlib.sha512).hexdigest()

        resp = requests.post(
            self.BASE_URL + '/verify',
            headers={
                'Authorization': 'Bearer ' + self.merchant_id
            },
            data={
                'ref_num': ref_num,
                'amount': amount,
                'sign': sign
            },
            timeout=30,
        )

        data = resp.json()

        if data['status'] == 1:
            with WalletPipeline() as pipeline:
                payment.accept(pipeline, payment.ref_id)

        else:
            payment.status = CANCELED
            payment.ref_status = data['status']
            payment.save()

            payment_request.details += f'verify status code: {resp.status_code}\n'
            payment_request.details += f'verify body: {data}'
            payment_request.save(update_fields=['details'])

    class Meta:
        proxy = True
