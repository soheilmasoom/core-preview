import logging

from django.db import transaction
from django.http import HttpResponseBadRequest
from django.views.generic import TemplateView

from financial.models import Gateway
from financial.utils.ipg import get_active_payment_request_by_authority
from ledger.utils.fields import CANCELED, PENDING

logger = logging.getLogger(__name__)


class ZibalCallbackView(TemplateView):
    authentication_classes = permission_classes = ()

    def get(self, request, *args, **kwargs):

        status = request.GET.get('success')
        authority = request.GET.get('trackId')

        if status not in ['1', '0']:
            return HttpResponseBadRequest('Invalid data')

        payment_request = get_active_payment_request_by_authority(authority, Gateway.ZIBAL)
        payment = payment_request.payment

        if not payment:
            with transaction.atomic():
                payment = payment_request.get_or_create_payment()

        if payment.status == PENDING:
            if status == '0':
                payment.status = CANCELED
                payment.save(update_fields=['status'])
            else:
                payment_request.get_gateway().verify(payment)

        return payment.redirect_to_app()
