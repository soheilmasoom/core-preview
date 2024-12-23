from django.urls import path
from .views import TreasuryViewSet

urlpatterns = [
    path('', TreasuryViewSet.as_view({'get': 'list'})),
    path('<int:pk>/', TreasuryViewSet.as_view({'get': 'retrieve'})),
]
