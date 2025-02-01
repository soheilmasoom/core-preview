from django.urls import path
from .views import HighlightListView, StorySeenAPIView

urlpatterns = [
    path('highlights/', HighlightListView.as_view(), name='highlight-list'),
    path('story/<int:pk>/seen/', StorySeenAPIView.as_view(), name='story-seen'),
]