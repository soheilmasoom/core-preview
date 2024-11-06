from rest_framework import serializers
from multimedia.models import FAQ
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

class FAQItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['question_text', 'answer_text', 'title', 'link']

    def to_representation(self, instance):
        if instance.type == FAQ.LINK:
            return {
                'title': instance.title,
                'link': instance.link
            }
        else:
            return {
                'question_text': instance.question_text,
                'answer_text': instance.answer_text
            }

class FAQResponseSerializer(serializers.Serializer):
    type = serializers.CharField()
    result = FAQItemSerializer(many=True)

class FAQByCategoryView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = FAQResponseSerializer

    def list(self, request, *args, **kwargs):
        slug = self.kwargs['slug']
        faqs = FAQ.objects.filter(category__slug=slug)

        if not faqs.exists():
            raise NotFound(f"پیدا نشد : {slug}")

        faq_type = faqs.first().type

        serializer = self.get_serializer({
            'type': faq_type,
            'result': faqs
        })
        return Response(serializer.data)