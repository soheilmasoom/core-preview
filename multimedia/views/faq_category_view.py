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
        fields = ['id', 'title', 'faqs']


class FAQCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FAQCategory.objects.all()
    serializer_class = FAQCategorySerializer


# class FAQViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = FAQ.objects.all()
#     serializer_class = FAQSerializer


class FAQByCategoryView(ListAPIView):
    serializer_class = FAQSerializer

    def get_queryset(self):
        category_id = self.kwargs['category_id']
        return FAQ.objects.filter(category_id=category_id)


# from rest_framework import serializers
# from multimedia.models import FAQCategory, FAQ
# from rest_framework import viewsets


# class FAQSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = FAQ
#         fields = ['id', 'question_text', 'answer_text']


# class FAQCategorySerializer(serializers.ModelSerializer):
#     faqs = FAQSerializer(many=True, read_only=True)

#     class Meta:
#         model = FAQCategory
#         fields = ['id', 'title', 'faqs']


# class FAQCategoryViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = FAQCategory.objects.all()
#     serializer_class = FAQCategorySerializer


# class FAQViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = FAQ.objects.all()
#     serializer_class = FAQSerializer
