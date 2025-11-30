import logging
from datetime import datetime

from celery import shared_task
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from accounts.models import Account
from ledger.models import Trx, Wallet
from ledger.utils.wallet_pipeline import WalletPipeline
from stake.models import StakeRequest, StakeRevenue

logger = logging.getLogger(__name__)


@shared_task(queue='celery')
def create_stake_revenue(now: datetime = None):

    if now:
        stake_requests = StakeRequest.objects.filter(
            Q(end_at__isnull=True) | Q(end_at__gt=now),
            Q(cancel_request_at__isnull=True) | Q(cancel_request_at__gt=now),
            Q(cancel_pending_at__isnull=True) | Q(cancel_pending_at__gt=now),
            start_at__lte=now,
        )
    else:
        stake_requests = StakeRequest.objects.filter(status=StakeRequest.DONE)
        now = timezone.now()

    system = Account.system()
    for stake_request in stake_requests:
        asset = stake_request.stake_option.asset
        revenue = stake_request.amount * stake_request.stake_option.apr / 100 / 365

        try:
            with WalletPipeline() as pipeline:
                stake_revenue = StakeRevenue.objects.create(
                    stake_request=stake_request,
                    revenue=revenue,
                    wallet_source=Wallet.STAKE,
                    created=now,
                )
                pipeline.new_trx(
                    group_id=stake_revenue.group_id,
                    sender=asset.get_wallet(system, Wallet.STAKE),
                    receiver=asset.get_wallet(stake_request.account, Wallet.STAKE),
                    amount=revenue,
                    scope=Trx.STAKE_REVENUE
                )

        except IntegrityError:
            logger.info('duplicate stake_revenue')
