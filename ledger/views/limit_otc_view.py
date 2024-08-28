import logging
import django_filters
from django.db.models import Q

from ledger.models import OTCRequest, OTCTrade
from market.serializers.trade_serializer import AccountTradeSerializer
from market.views import AccountTradeHistoryView

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework import serializers
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from accounts.authentication import CustomJWTAuthentication, TradeTokenAuthentication

logger = logging.getLogger(__name__)

class CancelLimitOTCView(APIView):
    authentication_classes = (SessionAuthentication, TradeTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def post(self, request):
        serializer = CancelLimitOTCSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_id = serializer.data.get('id')

        try:
            cancel_otc = OTCTrade.get_untriggered_otc_trade_queryset().filter(id=cancel_id).first()
            if cancel_otc:
                cancel_otc.reject(is_user_canceled=True)
            else:
                return Response({"message": 'not found'}, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f'failed cancel limit otc due to {e}', extra={
                'e': e
            })
            return Response({"message": 'failed'}, status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'done'}, status=status.HTTP_200_OK)

class CancelLimitOTCSerializer(serializers.Serializer):
    id = serializers.IntegerField()
