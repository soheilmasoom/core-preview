import logging

from celery import shared_task
from django.db.models import QuerySet, Q
from django.utils import timezone

from ledger.models import NetworkAsset
from ledger.utils.provider import get_provider_requester

logger = logging.getLogger()


@shared_task(queue='celery')
def update_network_fees(network_assets: QuerySet = None):
    if not network_assets:
        network_assets = NetworkAsset.objects.filter(
            Q(can_withdraw=True, network__can_withdraw=True) | Q(can_deposit=True, network__can_deposit=True),
            asset__enable=True,
        ).distinct()

    now = timezone.now()

    for ns in network_assets:
        info = get_provider_requester().get_network_info(ns.asset.symbol, ns.network.symbol)
        if not info:
            logger.info('Ignoring network asset update for (%s, %s) because of no data provided' % (ns.asset, ns.network))
            continue

        info = info[0]

        ns.update_with_provider(info, now)
