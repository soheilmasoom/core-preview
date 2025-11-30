from django.urls import path

from analytics import views

urlpatterns = [
    path('marketing/reports/', views.request_source_analytics),
    path('marketing/reports/download/', views.get_source_analytics),
]
