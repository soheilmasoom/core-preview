from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TreasuryViewSet

urlpatterns = [
    path('', TreasuryViewSet.as_view({'get': 'list'})),
    path('<int:pk>/', TreasuryViewSet.as_view({'get': 'retrieve'})),
]
