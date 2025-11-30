from rest_framework import serializers
from rest_framework.generics import ListAPIView

from ledger.models import CoinCategory


class CoinCategorySerializer(serializers.ModelSerializer):
    header = serializers.SerializerMethodField()

    def get_header(self, category: CoinCategory):
        return category.header or 'قیمت لحظه‌ای ارز‌های دیجیتال'

    class Meta:
        model = CoinCategory
        fields = ('name', 'title', 'description', 'header', 'meta_description')


class CoinCategoryListView(ListAPIView):
    permission_classes = ()
    serializer_class = CoinCategorySerializer
    queryset = CoinCategory.objects.all()
