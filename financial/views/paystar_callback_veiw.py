import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from rest_framework.exceptions import ValidationError

from financial.models import PaymentRequest, Gateway, Payment
from ledger.utils.fields import CANCELED, PENDING

logger = logging.getLogger(__name__)


class PaystarCallbackView(TemplateView):
    authentication_classes = permission_classes = ()

    def get(self, request, *args, **kwargs):
        status = request.GET.get('status')
        authority = request.GET.get('ref_num')
        tracking_code = request.GET.get('tracking_code')
        card_number = request.GET.get('card_number') or ''

        if not authority:
            raise ValidationError('no authority')

        payment_request = get_object_or_404(PaymentRequest, authority=authority, gateway__type=Gateway.PAYSTAR)
        payment = getattr(payment_request, 'payment', None)

        if not payment:
            with transaction.atomic():
                payment = payment_request.get_or_create_payment()
                payment.ref_id = tracking_code
                payment.card_pan = card_number
                payment.save(update_fields=['ref_id', 'card_pan'])

        if payment.status == PENDING:
            if status != '1':
                payment.status = CANCELED
                payment.save()
            else:
                payment_request.get_gateway().verify(payment)

        return payment.redirect_to_app()
