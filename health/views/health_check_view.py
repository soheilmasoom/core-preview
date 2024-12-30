import dataclasses
import logging
import random
from datetime import timedelta
from typing import List

from decouple import config
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from minio import Minio
from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.models import NetworkAsset, MarginPosition, MarginHistoryModel, Wallet
from ledger.utils.external_price import fetch_external_price, SIDES


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MonitorDTO:
    title: str
    detail: str
    link: str = ''


def short_join(l: list, max_count: int = 5):
    if len(l) > max_count:
        return ', '.join(map(str, l[:max_count])) + ', ...'

    return ', '.join(map(str, l))


def get_prices_unhealthy() -> List[MonitorDTO]:
    dead_monitors = []

    symbols = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'GORILLAUSDT', 'SOLUSDT']
    missing_prices = []

    for s in symbols:
        side = random.choice(SIDES)
        if not fetch_external_price(symbol=s, side=side, allow_stale=False):
            missing_prices.append(s)

    if missing_prices:
        dead_monitors.append(
            MonitorDTO(
                title='Missing External Prices',
                detail=f'No price fetched for {short_join(missing_prices)}'
            )
        )

    stale_network_assets = NetworkAsset.objects.filter(
        NetworkAsset.get_active_q(),
        update_with_provider=True,
        last_provider_update__lt=timezone.now() - timedelta(hours=6)
    )[:5].values('asset__symbol', 'network__symbol')

    stale_network_assets = list(map(lambda na: na['network__symbol'] + '/' + na['asset__symbol'], stale_network_assets))

    if stale_network_assets:
        dead_monitors.append(
            MonitorDTO(
                title='Stale Network Assets',
                detail=f'Updated 6h ago: {short_join(stale_network_assets)}',
                link=f'{settings.HOST_URL}/admin/ledger/networkasset/?active=1&update_with_provider__exact=1&o=12'
            )
        )

    return dead_monitors


def get_backups_unhealthy() -> List[MonitorDTO]:
    dead_monitors = []

    dead_backups = []

    for service in ['MASTERKEY', 'BLOCKLINK', 'PROVIDER']:
        service += '_BACKUP'
        endpoint = config(f'{service}_MINIO_CDN_ENDPOINT', None)

        if not endpoint:
            continue

        client = Minio(
            endpoint,
            access_key=config(f'{service}_MINIO_ACCESS_KEY'),
            secret_key=config(f'{service}_MINIO_SECRET_KEY'),
            secure=False
        )
        bucket_name = config(f'{service}_BUCKET_NAME')
        objects = client.list_objects(bucket_name, recursive=True)
        latest_object = max(objects, key=lambda obj: obj.last_modified)
        if (latest_object and latest_object.last_modified < timezone.now() - timedelta(days=1) or
                latest_object.size < 1024):
            dead_backups.append(service + '_FAILED')

    if dead_backups:
        dead_monitors.append(
            MonitorDTO(
                title='Missing Backups',
                detail=f'No backup found in 24h for: {short_join(dead_backups)}',
            )
        )

    return dead_monitors


def get_positions_unhealthy() -> List[MonitorDTO]:
    dead_monitors = []

    now = timezone.now().astimezone()
    last_hour = 0
    for i in [0, 8, 16]:
        if 0 <= now.hour - i < 8:
            last_hour = i
    last_cycle = now.replace(hour=last_hour, minute=0, second=0)

    interest_fee_position_ids = set(
        MarginHistoryModel.objects.filter(
            created__gte=timezone.now() - timedelta(days=1),
            type=MarginHistoryModel.INTEREST_FEE
        ).values_list('position_id', flat=True)
    )

    missed_interest_fee_positions = set(
        MarginPosition.objects.filter(
            status=MarginPosition.OPEN,
            liquidation_price__isnull=False,
            trade__created__lte=last_cycle
        ).exclude(
            id__in=interest_fee_position_ids
        ).values_list('id', flat=True).order_by('id')[:6])

    if missed_interest_fee_positions:
        dead_monitors.append(MonitorDTO(
            title='Missing Positions Interest Fee',
            detail=f'No interest fee created for positions: {short_join(missed_interest_fee_positions)}',
        ))

    lost_positions_liquidation_price = list(
        MarginPosition.objects.filter(
            ~Q(asset_wallet__balance=0),
            status=MarginPosition.OPEN,
            liquidation_price__isnull=True
        ).exclude(trade__isnull=True).values_list('id', flat=True).order_by('id')[:6])

    if lost_positions_liquidation_price:
        dead_monitors.append(
            MonitorDTO(
                title='No Positions Liquidation Price',
                detail=f'No liquidation price set for positions: {short_join(lost_positions_liquidation_price)}',
            )
        )

    closed_positions_wallets = list(
        Wallet.objects.filter(
            market=Wallet.MARGIN,
            variant__isnull=False
        ).exclude(
            Q(base_wallet__status='open') | Q(asset_wallet__status='open')
        ).exclude(balance=0).order_by('id').values_list('id', flat=True)[:6]
    )

    if closed_positions_wallets:
        dead_monitors.append(
            MonitorDTO(
                title='Closed Positions with Asset',
                detail=f'Closed positions non zero wallets: {short_join(closed_positions_wallets, 50)}',
                link=f'{settings.HOST_URL}/admin/ledger/marginposition/?balance_mismatched=1'

            )
        )

    return dead_monitors


class HealthCheckView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        unhealthy_monitors = [
            *get_backups_unhealthy(),
            *get_positions_unhealthy(),
            *get_prices_unhealthy(),
        ]

        if unhealthy_monitors:
            return Response({'status': 'dead', 'reason': list(map(dataclasses.asdict, unhealthy_monitors))})
        else:
            return Response({'status': 'healthy'})
