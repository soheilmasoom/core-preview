from rest_framework import serializers, viewsets
from multimedia.models import FAQCategory, FAQ
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['id', 'question_text', 'answer_text']


class FAQCategorySerializer(serializers.ModelSerializer):
    faqs = FAQSerializer(many=True, read_only=True)

    class Meta:
        model = FAQCategory
        fields = ['slug', 'title', 'faqs']


class FAQByCategoryView(ListAPIView):
    serializer_class = FAQSerializer

    def get_queryset(self):
        slug = self.kwargs['slug']
        return FAQ.objects.filter(category__slug=slug)
