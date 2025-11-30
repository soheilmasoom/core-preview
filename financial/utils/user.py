from django.db.models import Sum
from django.utils import timezone

from accounts.models import User
from financial.models import Payment
from ledger.utils.fields import DONE


def get_today_fiat_ipg_deposits(user: User):
    today = timezone.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

    return Payment.objects.filter(
        user=user,
        created__gte=today,
        status=DONE,
        paymentrequest__isnull=False
    ).aggregate(
        total=Sum('amount')
    )['total'] or 0
