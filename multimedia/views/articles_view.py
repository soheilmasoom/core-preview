from django.contrib.postgres.search import SearchVector
from rest_framework import serializers
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from multimedia.models import Section, Article


class ArticleMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ('id', 'title', 'slug',)


class ArticleSerializer(serializers.ModelSerializer):
    content = serializers.CharField(source='_content_html')
    parents = serializers.SerializerMethodField()

    def get_parents(self, article: Article):
        parents = []
        parent = article.parent

        while parent:
            parents.append(SectionMiniSerializer(parent).data)
            parent = parent.parent

        return reversed(parents)

    class Meta:
        model = Article
        fields = ('id', 'slug', 'title', 'content', 'parents')


class SectionMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ('id', 'title', 'slug',)


class SectionSerializer(serializers.ModelSerializer):
    parent = SectionMiniSerializer()
    articles = serializers.SerializerMethodField()

    def get_articles(self, section: Section):
        queryset = Article.objects.filter(parent=section)
        serializer = ArticleMiniSerializer(queryset, many=True)
        return serializer.data

    class Meta:
        model = Section
        fields = ('id', 'title', 'description', 'icon', 'slug', 'parent', 'articles',)


class SectionsView(ListAPIView):
    permission_classes = []
    serializer_class = SectionSerializer
    queryset = Section.objects.all()


class ArticleView(RetrieveAPIView):
    permission_classes = []
    serializer_class = ArticleSerializer

    def get_object(self):
        kwargs = self.kwargs
        slug = kwargs.get('slug', '')
        return get_object_or_404(Article, slug=slug)


class ArticleSearchView(ListAPIView):
    permission_classes = []
    serializer_class = ArticleMiniSerializer
    queryset = Article.objects.all()
    paginate_by = 10

    def get_queryset(self):
        search_parameter = self.request.query_params.get('q', '')

        if not search_parameter:
            return Response({}, status=404)

        return super().get_queryset().annotate(
            search=SearchVector(
                'title', 'title_en', '_content_text', 'parent__title', 'parent__title_en', 'parent__description'
            )
        ).filter(search=search_parameter)


class PinnedArticlesView(ListAPIView):
    permission_classes = []
    serializer_class = ArticleMiniSerializer
    paginate_by = 10

    def get_queryset(self):
        return Article.objects.filter(parent__parent__slug=self.kwargs['slug'], is_pinned=True)
