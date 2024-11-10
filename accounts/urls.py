from django.contrib.admin.views.decorators import staff_member_required
from django.urls import path, include
from rest_framework import routers

from accounts import views
from accounts.views.jwt_views import CustomTokenObtainPairView, InternalTokenObtainPairView, TokenLogoutView, \
    SessionTokenObtainPairView, JWTTokenRefreshView
from accounts.views.user_view import CreateAuthToken

router = routers.DefaultRouter()

router.register(r'^referrals', views.ReferralViewSet, basename='referral')
urlpatterns = [
    path('token/', CustomTokenObtainPairView.as_view(), name='obtain_token'),
    path('token/refresh/', JWTTokenRefreshView.as_view(), name='token_refresh'),
    path('token/access/', SessionTokenObtainPairView.as_view(), name='session_token'),
    path('token/logout/', TokenLogoutView.as_view(), name='token_logout'),

    path('internal-token/', InternalTokenObtainPairView.as_view(), name='obtain_token_internal'),

    path('login/', views.LoginView.as_view()),
    path('logout/', views.LogoutView.as_view()),

    path('company/docs/', views.RegisterDocuments.as_view()),

    path('signup/init/', views.InitiateSignupView.as_view()),
    path('signup/', views.SignupView.as_view()),

    path('widget/signup/init/', views.InitiateSignupWidgetView.as_view()),
    path('widget/signup/', views.SignupWidgetView.as_view()),
    path('widget/user/', views.UserWidgetView.as_view()),

    path('otp/verify/', views.VerifyOTPView.as_view()),
    path('otp/send/', views.SendOTPView.as_view()),

    path('stats/', views.UserStatisticsView.as_view()),
    path('user/', views.UserDetailView.as_view()),

    path('forget/init/', views.InitiateForgetPasswordView.as_view()),
    path('forget/', views.ForgetPasswordView.as_view()),
    path('password/set/', views.SetPasswordView.as_view()),

    path('verify/basic/', views.BasicInfoVerificationViewSet.as_view({
        'get': 'retrieve',
        'post': 'update',
    })),

    path('verify/full/', views.FullVerificationViewSet.as_view({
        'get': 'retrieve',
        'post': 'update',
    })),

    path('verify/tel/init/', views.InitiateTelephoneVerifyView.as_view()),
    path('verify/tel/otp/', views.TelephoneOTPVerifyView.as_view()),

    path('verify/email/otp/', views.EmailVerifyView.as_view()),
    path('verify/email/verify/', views.EmailOTPVerifyView.as_view()),

    path('notifs/generate/', views.NotificationView.as_view()),
    path('notifs/', views.NotificationViewSet.as_view({
        'get': 'list',
    })),

    path('notifs/<int:pk>/', views.NotificationViewSet.as_view({
        'get': 'retrieve',
        'patch': 'partial_update',
    })),

    path('notifs/all/', views.ReadAllNotificationView.as_view()),
    path('password/', views.ChangePasswordView.as_view()),

    path('quiz/passed/', views.QuizPassedView.as_view()),

    path('phone/init/', views.InitiateChangePhone.as_view()),
    path('phone/',   views.ChangePhoneView.as_view()),

    path('phone/change/', views.ChangePhoneBeforeVerifyView.as_view()),

    path('api/token/', CreateAuthToken.as_view()),

    path('referrals/overview/', views.ReferralOverviewAPIView.as_view()),
    path('referrals/report/', views.ReferralReportAPIView.as_view()),
    path('fee/', views.TradingFeeView.as_view()),

    path('login/activity/', views.LoginActivityViewSet.as_view({
        'get': 'list',
        'delete': 'destroy_all',
    })),
    path('login/activity/<int:pk>/', views.LoginActivityViewSet.as_view({
        'delete': 'destroy'
    })),

    path('', include(router.urls)),

    path('prize/', views.PrizeView.as_view({
        'get': 'list'
    })),

    path('prize/<int:pk>/', views.PrizeView.as_view({
        'patch': 'partial_update'
    })),

    path('firebase/', views.FirebaseTokenView.as_view()),

    path('app/', views.AppStatusView.as_view()),

    path('shahkar/', staff_member_required(views.ShahkarCheckView.as_view())),
    path('shahkar/status/', staff_member_required(views.ShahkarStatusView.as_view())),

    path('attribution/', views.AttributionAPIView.as_view()),

    path('2fa/', views.TOTPView.as_view()),
    path('2fa/forget/init/', views.Forget2FAInitView.as_view()),
    path('2fa/forget/', views.Forget2FAView.as_view()),

    path('users/<int:pk>/', views.UserDigestView.as_view()),

    path('feedback/', views.UserFeedbackView.as_view()),

    path('notify/', views.NotifyView.as_view()),

    path('consultation/', views.ConsultationView.as_view()),

    path('telegram/bot/start/', views.GenerateTelegramLinkAPIView.as_view()),
    path('telegram/bot/user/', views.TelegramUserIdRetrieveView.as_view()),
    path('telegram/bot/login/', views.GenerateTelegramAccessTokenView.as_view()),
]
