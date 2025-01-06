from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView, get_object_or_404, ListAPIView

from multimedia.models import GuideGroup, Guide, GuideVariant


class GuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guide
        fields = ('id', 'title', 'image', 'description', 'link', 'video')


class GuidesSerializer(serializers.ModelSerializer):
    guides = GuideSerializer(many=True)

    class Meta:
        model = GuideVariant
        fields = ('id', 'slug', 'title', 'guides')


class GuideVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuideVariant
        fields = ('id', 'slug', 'title')


class GuidesView(RetrieveAPIView):
    permission_classes = []
    serializer_class = GuidesSerializer

    def get_object(self):
        variant = self.request.query_params.get('variant', 'default')
        return get_object_or_404(GuideVariant, group__slug=self.kwargs['slug'], slug=variant)


class GuideVariantsView(ListAPIView):
    permission_classes = []
    serializer_class = GuideVariantSerializer

    def get_queryset(self):
        guide_group = get_object_or_404(GuideGroup, slug=self.kwargs['slug'])
        return GuideVariant.objects.filter(group=guide_group)
