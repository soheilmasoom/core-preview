from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import SystemConfig


class ConfigView(APIView):

    def get(self, requests):
        sys = SystemConfig.get_system_config()

        return Response({'strategy_enable': sys.strategy_enable})
