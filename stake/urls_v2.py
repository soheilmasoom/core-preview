from django.urls import path, include

from stake.views import *

urlpatterns = [
    path('option/', StakeOptionGroupedAPIView.as_view()),
]
