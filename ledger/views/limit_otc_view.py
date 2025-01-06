import logging

from rest_framework import serializers
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CustomJWTAuthentication, TradeTokenAuthentication
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from ledger.models import OTCTrade

logger = logging.getLogger(__name__)


class CancelLimitOTCView(APIView):
    authentication_classes = (SessionAuthentication, TradeTokenAuthentication, CustomJWTAuthentication)
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def post(self, request):
        serializer = CancelLimitOTCSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_id = serializer.data.get('id')

        account = self.request.user.get_account()
        otc = get_object_or_404(OTCTrade, status=OTCTrade.PENDING, id=cancel_id, otc_request__account=account)
        otc.reject(is_user_canceled=True)

        return Response({'message': 'done'}, status=status.HTTP_200_OK)


class CancelLimitOTCSerializer(serializers.Serializer):
    id = serializers.IntegerField()
