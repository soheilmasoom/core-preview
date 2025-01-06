from django.conf import settings
from django.urls import path

from health.views import HealthReadyView, HealthCheckView, SleepView

urlpatterns = [
    path('ready/', HealthReadyView.as_view()),
    path('check/', HealthCheckView.as_view()),
]


if settings.DEBUG_OR_TESTING_OR_STAGING:
    urlpatterns.extend([
        path('sleep/', SleepView.as_view()),
    ])
