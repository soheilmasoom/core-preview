from django.urls import path
from gamify import views


urlpatterns = [
    path('missions/', views.MissionsAPIView.as_view(), ),
    path('missions/active/', views.ActiveMissionsAPIView.as_view(), ),
    path('voucher/', views.TotalVoucherAPIView.as_view(), ),
]
