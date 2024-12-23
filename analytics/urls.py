from django.urls import path

from analytics import views

urlpatterns = [
    path('marketing/reports/<str:group_id>/', views.request_source_analytics, name='marketing_reports'),
    path('marketing/reports/<str:group_id>/download/', views.get_source_analytics),
    path('trx/', views.TransactionView.as_view({'get': 'list'}), name='trx'),
    path('wallet/', views.WalletView.as_view({'get': 'list'}), name='wallet'),
]
