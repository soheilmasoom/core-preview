from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import serializers
from multimedia.models import FAQ, FAQCategory
from rest_framework.generics import RetrieveAPIView
from rest_framework.exceptions import NotFound
from django.shortcuts import get_object_or_404

class FAQItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['title', 'answer', 'link']


class FAQResponseSerializer(serializers.Serializer):
    type = serializers.CharField()
    result = FAQItemSerializer(many=True)


class FAQByCategoryView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = FAQResponseSerializer

    def get_queryset(self):
        slug = self.kwargs['slug']
        self.category = get_object_or_404(FAQCategory, slug=slug)
        return FAQ.objects.filter(category=self.category)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            raise NotFound(f"not_found: {self.category.slug}")

        faq_type = self.category.type
        serializer = self.get_serializer({
            'type': faq_type,
            'result': queryset
        })
        return Response(serializer.data)