from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, CreateAPIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from financial.direct_debit.getter import get_direct_debit_client
from financial.direct_debit.vandar_client import ExternalAPIError
from financial.models.direct_debit_bank import DirectDebitBank
from financial.models.direct_debit_connection import DirectDebitConnection
from financial.models.direct_debit_gateway import DirectDebitGateway
from financial.utils.bank import get_bank_from_slug


class BanksSerializer(serializers.ModelSerializer):
    info = serializers.SerializerMethodField()

    def get_info(self, direct_debit_bank: DirectDebitBank):
        bank = get_bank_from_slug(direct_debit_bank.bank)
        return bank and bank.as_dict()

    def validate(self, attrs):
        gateway = DirectDebitGateway.live_objects.first()
        if not gateway:
            raise ValidationError('امکان دریافت لیست بانک ها وجود ندارد.')
        return attrs

    class Meta:
        model = DirectDebitBank
        fields = (
            'id', 'info', 'max_withdrawal_amount', 'max_withdrawal_amount_per_transaction',
            'max_withdrawal_daily_count', 'max_validity_duration_days',
        )


class BanksView(ListAPIView):
    serializer_class = BanksSerializer

    def get_queryset(self):
        gateway = DirectDebitGateway.live_objects.first()
        return DirectDebitBank.live_objects.filter(gateway=gateway)


class DirectDebitConnectionSerializer(serializers.Serializer):
    url = serializers.SerializerMethodField(read_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        bank_slug = self.context.get('bank')

        gateway = DirectDebitGateway.live_objects.first()
        if not gateway:
            raise ValidationError('امکان پرداخت مستقیم وجود ندارد.')

        bank = DirectDebitBank.live_objects.filter(bank=bank_slug).first()
        if not bank:
            raise ValidationError('بانک با این شناسه یافت نشد.')

        attrs['gateway'] = gateway
        attrs['bank'] = bank
        attrs['user'] = user
        return attrs

    def get_url(self, url):
        return url

    def create(self, validated_data):
        gateway = validated_data['gateway']
        bank = validated_data['bank']
        user = validated_data['user']

        client = get_direct_debit_client(gateway)

        try:
            url = client.get_authorization_create_url(user, bank)
            return url
        except ExternalAPIError as e:
            raise ValidationError(e)

    def destroy(self, validated_data):
        gateway = validated_data['gateway']
        bank = validated_data['bank']
        user = validated_data['user']

        connection = DirectDebitConnection.objects.filter(user=user, bank=bank, deleted=False).first()
        if not connection:
            raise ValidationError('مجوز با این مشخصات یافت نشد.')

        client = get_direct_debit_client(gateway)

        try:
            client.cancel_authorization_id(connection)
            return {'مجوز با موفقیت لغو شد.'}
        except ExternalAPIError as e:
            raise ValidationError(e)

    class Meta:
        fields = ('url',)


class DirectDebitConnectionView(ModelViewSet):
    serializer_class = DirectDebitConnectionSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        return {
            **ctx,
            'bank': self.kwargs['bank']
        }

    def destroy(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        result = serializer.destroy(serializer.validated_data)
        return Response(result)


class DirectDebitSerializer(serializers.Serializer):
    amount = serializers.DecimalField(write_only=True, max_digits=20, decimal_places=2, required=True)

    def validate(self, attrs):
        amount = attrs.get('amount')
        bank_slug = self.context.get('bank')
        user = self.context['request'].user

        gateway = DirectDebitGateway.live_objects.first()
        if not gateway:
            raise ValidationError('امکان پرداخت مستقیم وجود ندارد.')

        if user.level <= User.LEVEL2:
            raise ValidationError({'user': 'ابتدا احراز هویت کنید.'})

        bank = DirectDebitBank.live_objects.filter(bank=bank_slug).first()
        if not bank:
            raise ValidationError('بانک با این شناسه یافت نشد.')

        connection = DirectDebitConnection.objects.filter(user=user, bank=bank, deleted=False).first()
        if not connection:
            raise ValidationError('مجوز با این مشخصات یافت نشد.')

        if not connection.verified:
            raise ValidationError('مجوز با این مشخصات تایید نشده است.')

        attrs['bank'] = bank
        attrs['connection'] = connection

        return attrs

    def create(self, validated_data):
        bank = validated_data['bank']
        connection = validated_data['connection']
        amount = validated_data['amount']

        client = get_direct_debit_client(bank.gateway)

        try:
            client.create_payment_data(connection, amount)
            return Response({'واریز با موفقیت انجام شد.'})
        except ExternalAPIError as e:
            raise ValidationError(e)


class DirectDebitView(CreateAPIView):
    serializer_class = DirectDebitSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        return {
            **ctx,
            'bank': self.kwargs['bank']
        }
