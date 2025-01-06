from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView

from multimedia.models import FAQ, FAQCategory


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['title', 'answer', 'link']


class FAQCategorySerializer(serializers.ModelSerializer):
    faqs = FAQSerializer(many=True)

    class Meta:
        model = FAQCategory
        fields = ('type', 'faqs')


class FAQByCategoryView(RetrieveAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = FAQCategorySerializer

    def get_object(self):
        return get_object_or_404(FAQCategory, slug=self.kwargs['slug'])
