import logging
import time

from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class SleepView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        t = int(request.query_params.get('time', 10))

        t = min(100, max(1, t))

        time.sleep(t)

        return Response({'status': f'slept {t} seconds'})
