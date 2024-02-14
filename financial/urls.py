from django.urls import path

from financial.views import PaymentRequestView, ZarinpalCallbackView, BankCardView, PaymentHistoryView, \
    WithdrawRequestView, WithdrawHistoryView, BankAccountView, PaydotirCallbackView, ZibalCallbackView, \
    ProxyPaymentRedirectView, JibitCallbackView, GatewayInfoView, JibitPaymentIdCallbackView, PaymentIdViewsSet, \
    JibimoCallbackView, PaystarCallbackView, NovinpalCallbackView

urlpatterns = [
    path('payment/request/', PaymentRequestView.as_view()),
    path('payments/', PaymentHistoryView.as_view()),
    path('payment/go/', ProxyPaymentRedirectView.as_view()),
    path('payment/callback/zarinpal/', ZarinpalCallbackView.as_view(), name='zarinpal-callback'),
    path('payment/callback/paydotir/', PaydotirCallbackView.as_view(), name='paydotir-callback'),
    path('payment/callback/zibal/', ZibalCallbackView.as_view(), name='zibal-callback'),
    path('payment/callback/jibit/', JibitCallbackView.as_view(), name='jibit-callback'),
    path('payment/callback/jibimo/', JibimoCallbackView.as_view(), name='jibimo-callback'),
    path('payment/callback/novinpal/', NovinpalCallbackView.as_view(), name='novinpal-callback'),
    path('payment/callback/paystar/', PaystarCallbackView.as_view(), name='paystar-callback'),
    path('cards/', BankCardView.as_view({
        'get': 'list',
        'post': 'create'
    })),
    path('cards/<int:pk>/', BankCardView.as_view({
        'get': 'retrieve',
        'delete': 'destroy'
    })),
    path('accounts/', BankAccountView.as_view({
        'get': 'list',
        'post': 'create'
    })),
    path('accounts/<int:pk>/', BankAccountView.as_view({
        'get': 'retrieve',
        'delete': 'destroy'
    })),
    path('withdraw/request/', WithdrawRequestView.as_view({
        'post': 'create',
    })),
    path('withdraw/request/<int:pk>/', WithdrawRequestView.as_view({
        'delete': 'destroy'
    })),
    path('withdraw/list/', WithdrawHistoryView.as_view()),
    path('gateways/active/', GatewayInfoView.as_view()),

    path('paymentId/', PaymentIdViewsSet.as_view({
        'get': 'retrieve',
        'post': 'create',
    })),
    path('paymentId/callback/jibit/', JibitPaymentIdCallbackView.as_view(), name='jibit-paymentIds-callback'),
]
