from datetime import timedelta

from django.utils import timezone
from rest_framework.generics import get_object_or_404

from financial.models import PaymentRequest


def get_active_payment_request_by_authority(authority: str, gateway_type: str) -> PaymentRequest:
    return get_object_or_404(
        PaymentRequest,
        authority=authority,
        created__gte=timezone.now() - timedelta(hours=1),
        gateway__type=gateway_type,
        gateway__active=True,
        gateway__ipg_deposit_enable=True
    )
