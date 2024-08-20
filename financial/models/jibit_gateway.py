import requests
from decouple import config
from django.conf import settings
from rest_framework.reverse import reverse
from typing import Union
from accounts.models.user import User

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed, logger
from ledger.utils.fields import DONE, CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline
from rest_framework.exceptions import NotFound


class JibitGateway(Gateway):
    BASE_URL = 'https://napi.jibit.ir/ppg'
    _token = None

    def _get_token(self, force_renew: bool = False):
        if not force_renew:
            if self._token:
                return self._token

        resp = requests.post(
            url=self.BASE_URL + '/v3/tokens',
            json={
                'apiKey': self.deposit_api_key,
                'secretKey': self.deposit_api_secret,
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            self._token = resp_data['accessToken']

            return self._token

    def create_payment_request(self, user: User, amount: int, source: str, bank_card: Union['BankCard', None]) -> PaymentRequest:
        token = self._get_token()
        base_url = config('PAYMENT_PROXY_HOST_URL', default='') or settings.HOST_URL

        fee = self.get_ipg_fee(amount)

        payment_request = PaymentRequest.objects.create(
            user=user,
            bank_card=bank_card,
            amount=amount - fee,
            fee=fee,
            gateway=self,
            source=source,
        )

        payload = {
            'amount': amount * 10,
            'callbackUrl': base_url + reverse('finance:jibit-callback'),
            'clientReferenceNumber': str(payment_request.id),
            'currency': 'IRR',
            'description': 'افزایش اعتبار',
        }

        if bank_card:
            payload['payerCardNumber'] = bank_card.card_pan

        resp = requests.post(
            self.BASE_URL + '/v3/purchases',
            headers={'Authorization': 'Bearer ' + token},
            json=payload,
            timeout=30,
        )

        if not resp.ok:
            logger.info('jibit gateway connection error %s' % resp.json())
            raise GatewayFailed

        authority = resp.json()['purchaseId']
        payment_request.authority = authority
        payment_request.save(update_fields=['authority'])

        return payment_request

    def get_initial_redirect_url(self, payment_request: PaymentRequest) -> str:
        payment_proxy = config('PAYMENT_PROXY_HOST_URL', default='')

        if not payment_proxy:
            return super().get_initial_redirect_url(payment_request)
        else:
            return payment_proxy + '/api/v1/finance/payment/go/?gateway={gateway}&authority={authority}'.format(
                gateway=self.JIBIT,
                authority=payment_request.authority
            )

    @classmethod
    def get_payment_url(cls, payment_request: PaymentRequest):
        return 'https://napi.jibit.ir/ppg/v3/purchases/{}/payments'.format(payment_request.authority)

    def _verify(self, payment: Payment):
        payment_request = payment.paymentrequest
        token = self._get_token()
        resp = requests.post(
            headers={'Authorization': 'Bearer ' + token},
            url=self.BASE_URL + '/v3/purchases/{purchaseId}/verify'.format(purchaseId=payment_request.authority),
            timeout=30,
        )

        status = resp.json()['status']

        if status == 'ALREADY_VERIFIED':
            logger.warning('duplicate verify!', extra={'payment_id': payment.id})

        if status in ('SUCCESSFUL', 'ALREADY_VERIFIED'):
            with WalletPipeline() as pipeline:
                payment.accept(pipeline)

        else:
            logger.info(f'Jibit deposit (payment={payment.id}) canceled due to verification: {status}')
            payment.status = CANCELED
            payment.save(update_fields=['status', 'ref_status'])

    class Meta:
        proxy = True
