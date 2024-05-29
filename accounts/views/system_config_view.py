from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView

from accounts.models import SystemConfig


class SystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfig
        fields = ('id', 'dust_convert_threshold')


class SystemConfigView(RetrieveAPIView):
    permission_classes = []
    serializer_class = SystemConfigSerializer

    def get_object(self):
        return SystemConfig.get_system_config()
