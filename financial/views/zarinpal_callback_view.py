import logging

from django.db import transaction
from django.http import HttpResponseBadRequest
from django.views.generic import TemplateView

from financial.models import Gateway
from financial.utils.ipg import get_active_payment_request_by_authority
from ledger.utils.fields import CANCELED, PENDING

logger = logging.getLogger(__name__)


class ZarinpalCallbackView(TemplateView):
    authentication_classes = permission_classes = ()

    def get(self, request, *args, **kwargs):
        status = request.GET.get('Status')
        authority = request.GET.get('Authority')

        if status not in ['OK', 'NOK']:
            return HttpResponseBadRequest('Invalid data')

        payment_request = get_active_payment_request_by_authority(authority, Gateway.ZARINPAL)
        payment = getattr(payment_request, 'payment', None)

        if not payment:
            with transaction.atomic():
                payment = payment_request.get_or_create_payment()

        if payment.status == PENDING:
            if status == 'NOK':
                payment.status = CANCELED
                payment.save()
            else:
                payment_request.get_gateway().verify(payment)

        return payment.redirect_to_app()
