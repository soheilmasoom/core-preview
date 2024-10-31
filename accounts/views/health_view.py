import logging
from datetime import timedelta

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


class PriceHealthView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        symbols = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'GORILLAUSDT']

        missing_prices = []

        errors = {}

        for s in symbols:
            for side in SIDES:
                if fetch_external_price(symbol=s, side=side, allow_stale=False) is None:
                    missing_prices.append(s)

        if missing_prices:
            errors['missing_prices'] = missing_prices

        stale_network_assets = NetworkAsset.objects.filter(
            NetworkAsset.get_active_q(),
            update_with_provider=True,
            last_provider_update__lt=timezone.now() - timedelta(hours=6)
        ).count()

        if stale_network_assets:
            errors['stale_network_assets'] = stale_network_assets

        if errors:
            return Response({'status': 'dead', 'errors': errors})
        else:
            return Response({'status': 'healthy!'})


logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        unhealthy_services = []

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
                unhealthy_services.append(service + '_FAILED')
        now = timezone.now().astimezone()
        min = 8
        last_hour = 0
        for i in [0, 8, 16]:
            if 0 <= now.hour - i < min:
                last_hour = i
        last_cycle = now.replace(hour=last_hour, minute=0, second=0)

        position_ids = set(MarginHistoryModel.objects.filter(created__gte=timezone.now() - timedelta(days=1), type=MarginHistoryModel.INTEREST_FEE).values_list('position_id', flat=True))

        missed_position = set(MarginPosition.objects.filter(status=MarginPosition.OPEN, liquidation_price__isnull=False, trade__created__lte=last_cycle).exclude(id__in=position_ids).values_list('id', flat=True))
        if missed_position:
            unhealthy_services.append(f'Missed position INTEREST_FEE: {missed_position}')

        lost_positions = set(MarginPosition.objects.filter(~Q(asset_wallet__balance=0), status=MarginPosition.OPEN, liquidation_price__isnull=True).exclude(trade__isnull=True).values_list('id', flat=True))
        if lost_positions:
            unhealthy_services.append(f'Lost position liquidation price: {lost_positions}')

        queryset = (Wallet.objects.filter(market='margin', variant__isnull=False)
                    .exclude(Q(base_wallet__status='open') | Q(asset_wallet__status='open')).exclude(balance=0))

        if queryset.count() > 0:
            unhealthy_services.append(f'Closed Position non zero wallets:{set(queryset.values_list("id", flat=True))}')

        if unhealthy_services:
            return Response({'status': 'dead', 'errors': unhealthy_services})
        else:
            return Response({'status': 'healthy!'})
