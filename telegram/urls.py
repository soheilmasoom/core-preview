from django.urls import path
from .views import GenerateTelegramLinkAPIView
from .views import GetUserInfoView, GetToken, GetUserId


urlpatterns = [
    path('generate-link/', GenerateTelegramLinkAPIView.as_view(), name='generate_telegram_link'),
    path('get-token/', GetToken.as_view(), name='get_telegram_token'),
    path('user-info/<int:user_id>/', GetUserInfoView.as_view(), name='get_user_info'),
    path('get-user-id/', GetUserId.as_view(), name='get_user_id'),
]
