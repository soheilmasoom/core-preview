from django.urls import path
from django.views.decorators.cache import cache_page

from multimedia.views import ImageCreateView, BannerListView, SectionsView, ArticleView, ArticleSearchView, \
    PinnedArticlesView, FileCreateView, LatestBlogPostsView, FAQByCategoryView, GuidesView, GuideVariantsView

urlpatterns = [
    path('image/', ImageCreateView.as_view()),
    path('file/', FileCreateView.as_view()),
    path('banners/', cache_page(300)(BannerListView.as_view())),
    path('faq/sections/', SectionsView.as_view()),
    path('faq/articles/<str:slug>/', ArticleView.as_view()),
    path('faq/articles/', ArticleSearchView.as_view()),
    path('faq/sections/<slug:slug>/recom/', PinnedArticlesView.as_view()),
    path('faqs/<slug:slug>/', cache_page(300)(FAQByCategoryView.as_view())),
    path('guides/<slug:slug>/', cache_page(300)(GuidesView.as_view())),
    path('guides/<slug:slug>/variants/', cache_page(300)(GuideVariantsView.as_view())),
    path('blog/posts/latest/', cache_page(3600)(LatestBlogPostsView.as_view())),
]
