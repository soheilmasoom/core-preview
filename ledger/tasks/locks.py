from celery import shared_task

from ledger.models import *
from ledger.utils.wallet_pipeline import *
from market.models import *


@shared_task(queue='celery')
def free_missing_locks():
    open_keys = set(BalanceLock.objects.filter(reason=WalletPipeline.TRADE, amount__gt=0).values_list('key', flat=True))

    open_keys -= set(Order.open_objects.values_list('group_id', flat=True))
    open_keys -= set(OTCTrade.objects.filter(status=OTCTrade.PENDING).values_list('group_id', flat=True))
    open_keys -= set(StopLoss.open_objects.values_list('group_id', flat=True))

    with WalletPipeline() as p:
        for k in open_keys:
            p.release_lock(k)

    print(f'locks freed: {len(open_keys)} {open_keys}')
