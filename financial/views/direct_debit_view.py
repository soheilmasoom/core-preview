from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from financial.direct_debit.getter import get_direct_debit_client
from financial.direct_debit.vandar_client import ExternalAPIError
from financial.models.authorization_id import AuthorizationId
from financial.models.direct_debit_bank import DirectDebitBank
from financial.models.direct_debit_gateway import DirectDebitGateway


class BanksSerializer(serializers.ModelSerializer):
    class Meta:
        model = DirectDebitBank
        fields = (
            'id', 'code', 'name', 'is_healthy_on_direct_debit',
            'max_withdrawal_amount', 'max_withdrawal_amount_per_transaction',
            'withdrawal_amount_currency', 'max_withdrawal_daily_count',
            'max_mandate_validity_duration', 'mandate_validity_duration_unit',
            'payer_authentication_type'
        )


class BanksView(APIView):
    serializer_class = BanksSerializer

    def get(self, request, *args, **kwargs):
        gateway = DirectDebitGateway.live_objects.first()

        if not gateway:
            raise ValidationError('امکان دریافت لیست بانک ها وجود ندارد.')

        banks = DirectDebitBank.live_objects.filter(gateway=gateway)

        serializer = BanksSerializer(banks, many=True)

        return Response(serializer.data)


class AuthorizationIdSerializer(serializers.Serializer):
    bank_id = serializers.IntegerField(required=True)

    def validate(self, attrs):
        bank_id = attrs.get('bank_id')
        user = self.context['request'].user

        gateway = DirectDebitGateway.live_objects.first()
        if not gateway:
            raise serializers.ValidationError('امکان پرداخت مستقیم وجود ندارد.')

        bank = DirectDebitBank.live_objects.filter(id=bank_id).first()
        if not bank:
            raise serializers.ValidationError('بانک با این شناسه یافت نشد.')

        attrs['gateway'] = gateway
        attrs['bank'] = bank

        return attrs


class AuthorizationIdView(APIView):
    def get(self, request, *args, **kwargs):
        serializer = AuthorizationIdSerializer(data=request.GET, context={'request': request})
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        gateway = validated_data['gateway']
        bank = validated_data['bank']
        user = request.user

        client = get_direct_debit_client(gateway)

        try:
            url = client.get_authorization_create_url(user, bank)
            return Response({'status': 1, 'url': url})
        except ExternalAPIError as e:
            return Response({'status': 0, 'message': f'{str(e)}'})

    def delete(self, request, *args, **kwargs):
        serializer = AuthorizationIdSerializer(data=request.GET, context={'request': request})
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        gateway = validated_data['gateway']
        bank = validated_data['bank']
        user = request.user

        auth_id = AuthorizationId.objects.filter(user=user, bank=bank, deleted=False).first()
        if not auth_id:
            raise ValidationError('مجوز با این مشخصات یافت نشد.')

        client = get_direct_debit_client(gateway)

        try:
            client.cancel_authorization_id(auth_id)
            return Response({'status': 1, 'message': 'مجوز با موفقیت لغو شد.'})
        except ExternalAPIError as e:
            return Response({'status': 0, 'message': f'{str(e)}'})


class DirectDebitSerializer(serializers.Serializer):
    bank_id = serializers.IntegerField(required=True)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=True)

    def validate(self, attrs):
        bank_id = attrs.get('bank_id')
        amount = attrs.get('amount')
        user = self.context['request'].user

        gateway = DirectDebitGateway.live_objects.first()
        if not gateway:
            raise serializers.ValidationError('امکان پرداخت مستقیم وجود ندارد.')

        if user.level <= User.LEVEL2:
            raise serializers.ValidationError({'user': 'ابتدا احراز هویت کنید.'})

        bank = DirectDebitBank.live_objects.filter(id=bank_id).first()
        if not bank:
            raise serializers.ValidationError('بانک با این شناسه یافت نشد.')

        auth_id = AuthorizationId.objects.filter(user=user, bank=bank, deleted=False).first()
        if not auth_id:
            raise serializers.ValidationError('مجوز با این مشخصات یافت نشد.')

        if not auth_id.verified:
            raise serializers.ValidationError('مجوز با این مشخصات تایید نشده است.')

        attrs['gateway'] = gateway
        attrs['bank'] = bank
        attrs['auth_id'] = auth_id

        return attrs


class DirectDebitView(APIView):
    def get(self, request, *args, **kwargs):
        serializer = DirectDebitSerializer(data=request.GET, context={'request': request})
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        gateway = validated_data['gateway']
        auth_id = validated_data['auth_id']
        amount = validated_data['amount']

        client = get_direct_debit_client(gateway)

        try:
            client.create_payment_data(auth_id, amount)
            return Response({'status': 1, 'message': 'واریز با موفقیت انجام شد.'})
        except ExternalAPIError as e:
            return Response({'status': 0, 'message': f'{str(e)}'})
