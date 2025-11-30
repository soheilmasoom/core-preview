from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView

from accounts.models import AppStatus


class AppStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppStatus
        fields = ('latest_version', 'force_update_version', 'apk_link')


class AppStatusView(RetrieveAPIView):
    serializer_class = AppStatusSerializer
    permission_classes = []

    def get_object(self):
        return AppStatus.get_active()
