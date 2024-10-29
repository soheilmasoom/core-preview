import logging

from django.db import transaction
from django.http import HttpResponseBadRequest
from django.views.generic import TemplateView
from rest_framework.response import Response
from rest_framework.views import APIView

from financial.models import Gateway
from financial.utils.ipg import get_active_payment_request_by_authority
from financial.utils.payment_id_client import get_payment_id_client
from ledger.utils.fields import CANCELED, PENDING

logger = logging.getLogger(__name__)


class JibitCallbackView(TemplateView):
    authentication_classes = permission_classes = ()

    def post(self, request, *args, **kwargs):
        status = request.POST['status']
        authority = request.POST['purchaseId']

        if status not in ('SUCCESSFUL', 'FAILED'):
            return HttpResponseBadRequest('Invalid data')

        payment_request = get_active_payment_request_by_authority(authority, Gateway.JIBIT)

        payment = getattr(payment_request, 'payment', None)

        if not payment:
            with transaction.atomic():
                payment = payment_request.get_or_create_payment(
                    card_pan=request.POST.get('payerMaskedCardNumber', '')
                )

        if payment.status == PENDING:
            if status == 'FAILED':
                logger.info(f'Jibit deposit (payment={payment.id}) canceled due to failed status')

                payment.status = CANCELED
                payment.save()
            else:
                payment_request.get_gateway().verify(payment)

        print('REDIRECTING', payment.get_redirect_url())

        return payment.redirect_to_app()


class JibitPaymentIdCallbackView(APIView):
    authentication_classes = permission_classes = ()

    def post(self, request):
        logger.info('jibit paymentId callback %s' % request.data)

        status = request.data['status']

        if status not in ('SUCCESSFUL', 'FAILED'):
            return HttpResponseBadRequest('Invalid data')

        external_ref = request.data['externalReferenceNumber']

        gateway = Gateway.get_active_pay_id_deposit()
        client = get_payment_id_client(gateway)

        client.create_payment_request(external_ref)

        return Response(201)
