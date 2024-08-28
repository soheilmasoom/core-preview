from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.generics import RetrieveAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.authentication import CustomJWTAuthentication, CustomTokenAuthentication
from accounts.models import User
from accounts.throttle import BursAPIRateThrottle, SustainedAPIRateThrottle
from ledger.models import Network, DepositAddress


class InputAddressSerializer(serializers.Serializer):
    coin = serializers.CharField()
    network = serializers.CharField()


class DepositAddressView(RetrieveAPIView):
    authentication_classes = (SessionAuthentication, CustomTokenAuthentication, CustomJWTAuthentication)
    serializer_class = InputAddressSerializer
    throttle_classes = [BursAPIRateThrottle, SustainedAPIRateThrottle]

    def retrieve(self, request, *args, **kwargs):
        if request.user.level < User.LEVEL2:
            raise ValidationError({'user': 'برای واریز ابتدا احراز هویت خود را تکمیل نمایید.'})

        serializer = InputAddressSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        data = serializer.data

        network = get_object_or_404(Network, symbol=data['network'], can_deposit=True)

        deposit_address = DepositAddress.get_deposit_address(account=request.user.get_account(), network=network)

        return Response(data={
            'address': deposit_address.address,
            'memo': deposit_address.address_key.memo
        })
