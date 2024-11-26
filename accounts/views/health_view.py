import dataclasses
import logging
from datetime import timedelta
from typing import List

from decouple import config
from django.db.models import Q
from django.utils import timezone
from minio import Minio
from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.models import NetworkAsset, MarginPosition, MarginHistoryModel, Wallet
from ledger.utils.external_price import fetch_external_price, SIDES


class HealthView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        return Response({'status': 'healthy!'})


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MonitorDTO:
    title: str
    message: str
    link: str = ''


def short_join(l: List[str], max_count: int = 5):
    if len(l) > max_count:
        return ', '.join(l[:max_count]) + ' ...'

    return ', '.join(l)


def get_price_dead() -> List[MonitorDTO]:
    symbols = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'GORILLAUSDT', 'SOLUSDT']

    missing_prices = []

    errors = []

    for s in symbols:
        for side in SIDES:
            if not fetch_external_price(symbol=s, side=side, allow_stale=False):
                missing_prices.append(s)

    if missing_prices:
        errors.append(
            MonitorDTO(
                title='Missing External Prices',
                message=f'No price fetched for {short_join(missing_prices)}'
            )
        )

    stale_network_assets = NetworkAsset.objects.filter(
        NetworkAsset.get_active_q(),
        update_with_provider=True,
        last_provider_update__lt=timezone.now() - timedelta(hours=6)
    )[:5].values('asset__symbol', 'network__symbol')

    stale_network_assets = list(map(lambda na: na['network__symbol'] + '/' + na['asset__symbol'], stale_network_assets))

    if stale_network_assets:
        errors.append(
            MonitorDTO(
                title='Stale Network Assets',
                message=f'Updated 6h ago: {short_join(stale_network_assets)}'
            )
        )

    return errors


def get_backup_dead() -> list:
    dead = []

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
            dead.append(service + '_FAILED')

    return dead


def get_positions_unhealthy():
    dead = []

    now = timezone.now().astimezone()
    last_hour = 0
    for i in [0, 8, 16]:
        if 0 <= now.hour - i < 8:
            last_hour = i
    last_cycle = now.replace(hour=last_hour, minute=0, second=0)

    position_ids = set(MarginHistoryModel.objects.filter(created__gte=timezone.now() - timedelta(days=1),
                                                         type=MarginHistoryModel.INTEREST_FEE).values_list(
        'position_id', flat=True))

    missed_position = set(MarginPosition.objects.filter(status=MarginPosition.OPEN, liquidation_price__isnull=False,
                                                        trade__created__lte=last_cycle).exclude(
        id__in=position_ids).values_list('id', flat=True))
    if missed_position:
        dead.append(f'Missed position INTEREST_FEE: {missed_position}')

    lost_positions = set(MarginPosition.objects.filter(~Q(asset_wallet__balance=0), status=MarginPosition.OPEN,
                                                       liquidation_price__isnull=True).exclude(
        trade__isnull=True).values_list('id', flat=True))
    if lost_positions:
        dead.append(f'Lost position liquidation price: {lost_positions}')

    queryset = (Wallet.objects.filter(market='margin', variant__isnull=False)
                .exclude(Q(base_wallet__status='open') | Q(asset_wallet__status='open')).exclude(balance=0))

    if queryset.count() > 0:
        dead.append(f'Closed Position non zero wallets:{set(queryset.values_list("id", flat=True))}')

    return dead


class HealthCheckView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        unhealthy_services = [
            *get_backup_dead(),
            *get_positions_unhealthy()
        ]

        if unhealthy_services:
            return Response({'status': 'dead', 'errors': unhealthy_services})
        else:
            return Response({'status': 'healthy!'})
