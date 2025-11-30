from django.urls import path, include
from django.views.decorators.cache import cache_page
from rest_framework import routers

from market.views import *

router = routers.DefaultRouter()
router.register(r'^orders', OrderViewSet, basename='order')
router.register(r'^stop-loss-orders', StopLossViewSet, basename='stop_loss')
router.register(r'^oco-orders', OCOViewSet, basename='oco')

urlpatterns = [
    path('irt/info/', cache_page(60)(MarketIRTInfoView.as_view())),
    path('usdt/info/', cache_page(60)(MarketUSDTInfoView.as_view())),

    path('depth/<str:symbol>/', OrderBookAPIView.as_view()),
    path('orders/cancel/', CancelOrderAPIView.as_view()),
    path('orders/bulk-cancel/', BulkCancelOrderAPIView.as_view()),
    path('symbols/spreads/', SymbolSpreadListView.as_view()),
    path('symbols/<str:name>/', cache_page(300)(SymbolDetailedStatsAPIView.as_view())),
    path('symbols/', SymbolListAPIView.as_view()),
    path('myTrades/', AccountTradeHistoryView.as_view()),
    path('trades/pairs/', TradePairsHistoryView.as_view()),
    path('trades/', cache_page(10)(TradeHistoryView.as_view())),
    path('tradingview/ohlcv/', cache_page(10)(OHLCVAPIView.as_view())),
    path('open-orders/', OpenOrderListAPIView.as_view()),
    path('', include(router.urls)),
    path('bookmark/', BookmarkSymbolAPIView.as_view()),
    path('discover/', MarketDiscoverView.as_view())
]
