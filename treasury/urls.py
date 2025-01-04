from django.urls import path
from .views import TreasuryViewSet, PhysicalWithdrawViewSet

urlpatterns = [
    # Treasury endpoints
    path('', TreasuryViewSet.as_view({'get': 'list'})),
    path('<int:pk>/', TreasuryViewSet.as_view({'get': 'retrieve'})),

    # Physical Withdraw endpoints
    path('withdraw/', PhysicalWithdrawViewSet.as_view({
        'get': 'list',
        'post': 'create'
    })),
    path('withdraw/<int:pk>/', PhysicalWithdrawViewSet.as_view({
        'get': 'retrieve'
    })),
]
