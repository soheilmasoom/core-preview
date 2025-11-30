import logging
from datetime import datetime, timedelta

import pytz
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Attribution, AttributionTracker, TrafficSource

logger = logging.getLogger(__name__)


class AttributionAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        self.handle_event(request.query_params)
        return Response(status=200)

    def handle_event(self, data: dict):
        logger.info(f'New attribution {data}')

        key = data.get('key')
        if not key:
            return

        tracker = AttributionTracker.objects.filter(key=key).first()

        if not tracker:
            raise ValidationError({
                'tracker': 'invalid'
            })

        to_update = {}

        for field_name in AttributionTracker.YANDEX_FIELDS.values():
            d = data.get(field_name)

            if not d:
                field = getattr(Attribution, field_name).field
                if not field.null:
                    d = ''

            if not (d and d.startswith('{')):
                to_update[field_name] = d

        for field_name in ('installed_at', 'clicked_at'):
            if to_update.get(field_name):
                to_update[field_name] = datetime.strptime(to_update.get(field_name), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.utc).astimezone()
                if to_update[field_name].year < 2020:
                    to_update[field_name] = None

        attribution, _ = Attribution.objects.get_or_create(
            tracker=tracker,
            **to_update
        )

        if attribution.profile_id:
            TrafficSource.objects.filter(
                utm_source='pwa_app',
                utm_medium='organic',
                yandex_profile_id=attribution.profile_id,
                created__gte=timezone.now() - timedelta(days=1)
            ).update(
                utm_medium=attribution.utm_medium,
                utm_campaign=attribution.utm_campaign,
                utm_content=attribution.utm_content,
            )
