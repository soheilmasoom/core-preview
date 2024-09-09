from django.urls import path

from search.views import *

urlpatterns = [
    path('', SearchView.as_view()),
    ]
