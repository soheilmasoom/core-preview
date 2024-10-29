from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView

from accounts.models import SystemConfig


class SystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfig
        fields = ('id', 'dust_convert_threshold', 'strategy_enable', 'min_fast_buy_irt', 'max_fast_buy_irt',
                  'min_otc_irt', 'max_otc_irt')


class SystemConfigView(RetrieveAPIView):
    permission_classes = []
    serializer_class = SystemConfigSerializer

    def get_object(self):
        return SystemConfig.get_system_config()
