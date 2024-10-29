from celery import shared_task
from django.db.models import Sum, Count, F

from accounts.models import User
from ledger.utils.fields import DONE


@shared_task()
def ban_credit_deposit_of_free_riders():
    from financial.models import FiatWithdrawRequest

    free_riders = FiatWithdrawRequest.objects.filter(
        status=DONE,
        bank_account__user__ban_deposit_with_credit_bank_cards=False
    ).values('bank_account__user_id').annotate(
        total_withdraws=Sum('amount'),
        count=Count('*'),
        total_trades=F('bank_account__user__account__trade_volume_irt')
    ).filter(total_withdraws__gte=10e6, count__gte=3, total_trades__lte=F('total_withdraws') * 0.01).values_list(
        'bank_account__user_id', flat=True
    )

    users = User.objects.filter(id__in=free_riders)

    for user in users:
        user.ban_deposit_by_credit_cards()
