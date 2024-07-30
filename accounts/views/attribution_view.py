import logging
from datetime import datetime

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Attribution, AttributionTracker

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

        Attribution.objects.get_or_create(
            tracker=tracker,
            **to_update
        )
