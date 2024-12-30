import logging

from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthReadyView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        return Response({'status': 'healthy!'})
