import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.authentication import CustomJWTAuthentication, CustomTokenAuthentication
from accounts.models import User, SystemConfig
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from market.models import PairSymbol
from market.serializers import BookMarkPairSymbolSerializer
from market.serializers.symbol_serializer import SymbolSerializer, SymbolBriefStatsSerializer, SymbolStatsSerializer
from market.utils.price import get_symbol_prices


class SymbolFilter(django_filters.FilterSet):
    asset = django_filters.CharFilter(field_name='asset__symbol')
    base_asset = django_filters.CharFilter(field_name='base_asset__symbol')

    class Meta:
        model = PairSymbol
        fields = ('name', 'asset', 'base_asset', 'enable', 'strategy_enable', 'margin_enable')


class SymbolListAPIView(ListAPIView):
    authentication_classes = (SessionAuthentication, CustomTokenAuthentication, CustomJWTAuthentication)
    permission_classes = ()
    filter_backends = [DjangoFilterBackend]
    filter_class = SymbolFilter
    filterset_fields = ('strategy_enable', 'margin_enable')

    def get_queryset(self):
        if self.request.query_params.get('include_hidden') == '1':
            queryset = PairSymbol.objects.filter(asset__enable=True).order_by(
                '-asset__trend', 'asset__order', 'base_asset__trend', '-base_asset__order'
            )
        else:
            queryset = PairSymbol.objects.filter(enable=True).order_by(
                '-asset__trend', 'asset__order', 'base_asset__trend', '-base_asset__order'
            )
        return queryset.prefetch_related('asset', 'base_asset')

    def get_serializer_class(self):
        if self.request.query_params.get('stats') == '1':
            return SymbolBriefStatsSerializer
        else:
            return SymbolSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            ctx['bookmarks'] = set(user.get_account().bookmark_market.values_list('id', flat=True))
        else:
            ctx['bookmarks'] = []

        ctx['prices'] = get_symbol_prices()
        ctx['system_config'] = SystemConfig.get_system_config()

        return ctx


class SymbolDetailedStatsAPIView(RetrieveAPIView):
    permission_classes = ()
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    serializer_class = SymbolStatsSerializer
    queryset = PairSymbol.objects.all()
    lookup_field = 'name'


class BookmarkSymbolAPIView(APIView):
    def patch(self, request):
        user = self.request.user
        book_mark_serializer = BookMarkPairSymbolSerializer(
            instance=user,
            data=request.data,
            partial=True
        )
        book_mark_serializer.is_valid(raise_exception=True)
        book_mark_serializer.save()
        return Response({'msg': 'ok'})

    def get_queryset(self):
        return User.objects.filter(user=self.request.user)
