import logging

from django.db import transaction
from django.views.generic import TemplateView
from rest_framework.exceptions import ValidationError

from financial.models import Gateway
from financial.utils.ipg import get_active_payment_request_by_authority
from ledger.utils.fields import CANCELED, PENDING

logger = logging.getLogger(__name__)


class PaystarCallbackView(TemplateView):
    authentication_classes = permission_classes = ()

    def get(self, request, *args, **kwargs):
        status = request.GET.get('status')
        authority = request.GET.get('ref_num', '')
        tracking_code = request.GET.get('tracking_code')
        card_number = request.GET.get('card_number', '')

        if not authority:
            raise ValidationError('no authority')

        payment_request = get_active_payment_request_by_authority(authority, Gateway.PAYSTAR)

        payment = getattr(payment_request, 'payment', None)

        if not payment:
            with transaction.atomic():
                payment = payment_request.get_or_create_payment(
                    ref_id=tracking_code,
                    card_pan=card_number
                )
        if payment.status == PENDING:
            if status != '1':
                payment.status = CANCELED
                payment.save()
            else:
                payment_request.get_gateway().verify(payment)

        return payment.redirect_to_app()
