from django.urls import path, include

from stake.views import *

urlpatterns = [
    path('request/', StakeRequestAPIView.as_view({'get': 'list', 'post': 'create'})),
    path('request/<int:pk>/', StakeRequestAPIView.as_view({'delete': 'destroy'})),
    path('option/', StakeOptionAPIView.as_view()),
    path('revenue/', StakeRevenueAPIView.as_view()),
    path('overview/', StakeOverviewAPIView.as_view()),
    path('wallets/', StakeWalletsAPIView.as_view()),
]
