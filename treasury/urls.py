from django.urls import path

from treasury.views import TreasuryListView, PhysicalWithdrawListView, PhysicalWithdrawDetailView, \
    PhysicalWithdrawInitView

urlpatterns = [
    path('treasury/', TreasuryListView.as_view(), name='treasury-list'),
    path('withdraw/', PhysicalWithdrawListView.as_view(), name='withdraw-list'),
    path('withdraw/<int:pk>/', PhysicalWithdrawDetailView.as_view(), name='withdraw-detail'),
    path('withdraw/init/', PhysicalWithdrawInitView.as_view(), name='withdraw-init'),

]
