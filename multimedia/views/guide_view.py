from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView, get_object_or_404

from multimedia.models import GuideGroup, Guide


class GuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guide
        fields = ('title', 'image', 'description', 'link', 'video')


class GuideGroupSerializer(serializers.ModelSerializer):
    guides = GuideSerializer(many=True)

    class Meta:
        model = GuideGroup
        fields = ('slug', 'title', 'guides')


class GuideGroupView(RetrieveAPIView):
    permission_classes = []
    serializer_class = GuideGroupSerializer

    def get_object(self):
        return get_object_or_404(GuideGroup, slug=self.kwargs['slug'])
