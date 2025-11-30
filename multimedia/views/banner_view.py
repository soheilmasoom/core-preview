from rest_framework import serializers
from rest_framework.generics import ListAPIView

from accounts.authentication import is_app
from multimedia.models import Banner


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ('id', 'title', 'image', 'link', 'app_link')


class BannerListView(ListAPIView):
    serializer_class = BannerSerializer
    permission_classes = []

    def get_queryset(self):
        banners = Banner.objects.filter(active=True)

        if is_app(self.request):
            banners = banners.exclude(limit=Banner.ONLY_DESKTOP)

        return banners
