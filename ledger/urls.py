from django.urls import path

from ledger import views

urlpatterns = [
    path('v1/assets/', views.AssetsViewSet.as_view({'get': 'list'})),
    path('v1/assets/categories/', views.CoinCategoryListView.as_view()),
    path('v1/networkassets/', views.NetworkAssetView.as_view()),
    path('v1/asset/overview/', views.AssetOverviewAPIView.as_view()),
    path('v1/price/alert/single/', views.AssetAlertViewSet.as_view({
        'post': 'create',
        'get': 'list',
        'delete': 'destroy',
    })),
    path('v1/price/alert/bulk/', views.BulkAssetAlertViewSet.as_view({
        'post': 'create',
        'get': 'list',
        'delete': 'destroy'
    })),
    path('v1/price/alert/switch/', views.PriceNotifSwitchView.as_view()),

    path('v1/networks/', views.BriefNetworkAssetsView.as_view()),

    path('v1/assets/reserve/', views.ReserveWalletCreateAPIView.as_view()),
    path('v1/assets/reserve/refund/', views.ReserveWalletRefundAPIView.as_view()),

    path('v1/assets/<slug:symbol>/', views.AssetsViewSet.as_view({'get': 'retrieve'})),

    path('v1/wallets/', views.WalletViewSet.as_view({'get': 'list'})),
    path('v1/wallets/<slug:symbol>/', views.WalletViewSet.as_view({'get': 'retrieve'})),
    path('v1/wallets/<slug:symbol>/balance/', views.WalletBalanceView.as_view()),
    path('v1/withdraw/feedback/categories/', views.FeedbackCategories.as_view()),
    path('v1/withdraw/feedback/', views.WithdrawFeedbackViewSet.as_view({'post': 'create'})),
    path('v1/withdraw/feedback/<int:pk>/', views.WithdrawFeedbackViewSet.as_view({'patch': 'partial_update'})),

    path('v1/deposit/address/', views.DepositAddressView.as_view()),

    path('v1/withdraw/', views.WithdrawView.as_view()),

    path('v1/withdraws/', views.WithdrawViewSet.as_view({
        'get': 'list'
    })),
    path('v1/withdraws/<int:pk>/', views.WithdrawViewSet.as_view({
        'delete': 'destroy'
    })),

    path('v1/withdraw/list/', views.WithdrawHistoryView.as_view()),
    path('v1/deposit/list/', views.DepositHistoryView.as_view()),

    path('v1/trade/otc/request/', views.OTCTradeRequestView.as_view()),
    path('v1/trade/otc/', views.OTCTradeView.as_view()),
    path('v1/trade/otc/info/', views.OTCInfoView.as_view()),
    path('v1/trade/otc/myTrades/', views.OTCHistoryView.as_view()),

    path('v1/margin/transfer/', views.MarginTransferViewSet.as_view({
        'get': 'list',
        'post': 'create'
    })),
    path('v1/margin/asset/interest/', views.MarginAssetInterestView.as_view()),

    path('v2/margin/wallets/', views.MarginAssetViewSet.as_view({'get': 'list'})),
    path('v2/margin/balance/', views.MarginBalanceAPIView.as_view()),
    path('v2/margin/transfer-balance/', views.MarginTransferBalanceAPIView.as_view()),
    path('v2/margin/positions/', views.MarginPositionViewSet.as_view({'get': 'list'})),
    path('v2/margin/close/', views.MarginClosePositionView.as_view()),
    path('v2/margin/info/', views.MarginInfoView.as_view()),
    path('v2/margin/position/info/', views.MarginPositionInfoView.as_view()),
    path('v2/margin/position/history/', views.MarginPositionHistoryView.as_view()),
    path('v2/margin/leverage/', views.MarginLeverageView.as_view()),

    path('v1/addressbook/<int:pk>/', views.AddressBookView.as_view({
        'get': 'retrieve',
        'delete': 'destroy',
    })),
    path('v1/addressbook/', views.AddressBookView.as_view({
        'post': 'create',
        'get': 'list',
    })),
    path('v2/addressbook/', views.AddressBookViewV2.as_view({
        'post': 'create',
        'get': 'list',
    })),

    path('v1/wallet/balance/', views.BalanceInfoView.as_view()),
    path('v1/funds/overview/', views.WalletsOverviewAPIView.as_view()),
    path('v1/bookmark/assets/', views.BookmarkAssetsAPIView.as_view()),

    path('v1/transfer/deposit/', views.DepositTransferUpdateView.as_view()),
    path('v1/transfer/withdraw/', views.WithdrawTransferUpdateView.as_view()),

    path('v1/convert/dust/', views.ConvertDustView.as_view()),
    path('v1/bookmark/assets/', views.BookmarkAssetsAPIView.as_view()),
    path('v1/pnl/overview/', views.PNLOverview.as_view()),

    path('v1/fast_buy/', views.FastBuyTokenAPI.as_view()),

    path('v1/transactions/recent/', views.RecentTransactionsView.as_view()),

    path('v1/deposit/recover/', views.DepositRecoveryView.as_view()),
]
