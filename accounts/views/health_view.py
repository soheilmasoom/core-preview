import requests
from datetime import timedelta

from decouple import config
from django.conf import settings
from django.utils import timezone
from minio import Minio
from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.models import NetworkAsset
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
            last_provider_update__lt=timezone.now() - timedelta(hours=6)
        ).count()

        if stale_network_assets:
            errors['stale_network_assets'] = stale_network_assets

        if errors:
            return Response({'status': 'dead', 'errors': errors})
        else:
            return Response({'status': 'healthy!'})


class HealthCheckView(APIView):
    def get(self, requests):
        unhealthy_services = []

        for service in ['MASTERKEY_', 'BLOCKLINK_', 'PROVIDER_']:
            service += 'BACKUP_'
            client = Minio(
                config(f'{service}MINIO_CDN_ENDPOINT'),
                access_key=config(f'{service}MINIO_ACCESS_KEY'),
                secret_key=config(f'{service}MINIO_SECRET_KEY'),
                secure=False
            )
            bucket_name = config(f'{service}BUCKET_NAME')
            objects = client.list_objects(bucket_name, recursive=True)
            latest_object = max(objects, key=lambda obj: obj.last_modified)
            if (latest_object and latest_object.last_modified < timezone.now() - timedelta(days=1) or
                    latest_object.size < 1024):
                unhealthy_services.append(service + 'BACKUP_FAILED')

        if unhealthy_services:
            return Response({'status': 'dead', 'errors': unhealthy_services})
        else:
            return Response({'status': 'healthy!'})
