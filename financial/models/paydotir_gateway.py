from typing import Union
import requests
from django.conf import settings
from django.urls import reverse
from decouple import config
from accounts.models.user import User

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed
from ledger.utils.fields import DONE, CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline
from rest_framework.exceptions import NotFound


class PaydotirGateway(Gateway):
    BASE_URL = 'https://pay.ir'

    def create_payment_request(self, user: User, amount: int, source: str, bank_card: Union['BankCard', None]) -> PaymentRequest:
        base_url = config('PAYMENT_PROXY_HOST_URL', default='') or settings.HOST_URL

        payload = {
                'api': self.merchant_id,
                'amount': amount * 10,
                'description': 'افزایش اعتبار',
                'redirect': base_url + reverse('finance:paydotir-callback'),
        },

        if bank_card:
            payload['validCardNumber'] = bank_card.card_pan
        else:
            raise NotImplementedError

        resp = requests.post(
            self.BASE_URL + '/pg/send',
            json=payload,
            timeout=30,
        )

        resp_data = resp.json()

        if not resp.ok or resp_data['status'] != 1:
            print('status code', resp.status_code)
            print('body', resp_data)

            raise GatewayFailed

        authority = resp.json()['token']

        return PaymentRequest.objects.create(
            user=user,
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
