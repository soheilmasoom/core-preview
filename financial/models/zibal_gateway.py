import logging
from typing import Union

import requests
from django.conf import settings
from django.urls import reverse
from accounts.models.system_config import SystemConfig
from accounts.models.user import User

from financial.models import Gateway, BankCard, PaymentRequest, Payment
from financial.models.gateway import GatewayFailed
from ledger.utils.fields import DONE, CANCELED
from ledger.utils.wallet_pipeline import WalletPipeline
from rest_framework.exceptions import NotFound


logger = logging.getLogger(__name__)


class ZibalGateway(Gateway):
    BASE_URL = 'https://gateway.zibal.ir'

    def create_payment_request(self, user: User, amount: int, source: str, bank_card: Union['BankCard', None]) -> PaymentRequest:
        callback_host = self.ipg_callback_host or settings.HOST_URL

        payload = {
            'merchant': self.merchant_id,
            'amount': amount * 10,
            'callbackUrl': callback_host + reverse('finance:zibal-callback'),
            'description': 'افزایش اعتبار'
        }

        if bank_card:
            payload['allowedCards'] = bank_card.card_pan
        elif SystemConfig.get_system_config().check_national_code_for_widget:
            if user.national_code:
                payload['nationalCode'] = user.national_code
            else:
                raise GatewayFailed('No national code')

        resp = requests.post(
            self.BASE_URL + '/v1/request',
            json=payload,
            timeout=30,
        )

        if resp.json()['result'] != 100:
            logger.info('zibal gateway connection error %s' % resp.json())
            raise GatewayFailed

        authority = resp.json()['trackId']
        fee = self.get_ipg_fee(amount)

        return PaymentRequest.objects.create(
            user=user,
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

    def _verify(self, payment: Payment):
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
