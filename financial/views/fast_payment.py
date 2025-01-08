from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, ListAPIView
from rest_framework.viewsets import ModelViewSet

from accounts.authentication import CustomTokenAuthentication
from accounts.models import User
from accounts.permissions import IsBasicVerified
from financial.fast_payment.getter import get_fast_payment_client
from financial.models.fast_payment_gateway import FastPaymentGateway


class BanksSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    is_healthy_on_direct_debit = serializers.BooleanField()
    max_withdrawal_amount = serializers.IntegerField()
    max_withdrawal_amount_per_transaction = serializers.IntegerField()
    withdrawal_amount_currency = serializers.CharField()
    max_withdrawal_daily_count = serializers.IntegerField(allow_null=True)
    max_mandate_validity_duration = serializers.IntegerField()
    mandate_validity_duration_unit = serializers.CharField()
    payer_authentication_type = serializers.CharField()
    logo = serializers.URLField()

    def get_banks(self):
        gateway = FastPaymentGateway.live_objects.first()

        if not gateway:
            raise ValidationError('امکان ساخت شناسه واریز وجود ندارد.')

        client = get_fast_payment_client(gateway)

        banks = client.get_banks()

        if not banks:
            raise ValidationError('مشکلی در دریافت اطاعات به وجود آمد. لطفا پس از مدتی دوباره تلاش کنید.')

        return banks


class BanksView(ListAPIView):
    authentication_classes = [CustomTokenAuthentication]
    permission_classes = [IsBasicVerified, ]
    serializer_class = BanksSerializer

    def get_queryset(self):
        return BanksSerializer().data


class AuthorizationIdSerializer(serializers.ModelSerializer):
    pay_id = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()

    def create(self, validated_data):
        user = self.context['request'].user

        if user.level <= User.LEVEL1:
            raise ValidationError({'user': 'ابتدا احراز هویت کنید.'})

        if not BankAccount.objects.filter(user=user, verified=True, deleted=False):
            raise ValidationError({'iban': 'شما باید حداقل یک حساب بانکی تایید شده داشته باشید.'})

        gateway = PaymentIdGateway.live_objects.first()

        if not gateway:
            raise ValidationError('امکان ساخت شناسه واریز وجود ندارد.')

        client = get_payment_id_client(gateway)

        payment_id = client.create_payment_id(user)

        if not payment_id:
            raise ValidationError('مشکلی در ساخت شناسه واریز به وجود آمد. لطفا پس از مدتی دوباره تلاش کنید.')

        return payment_id

    def get_pay_id(self, payment_id: PaymentId):
        if not payment_id.verified:
            return ''
        else:
            return payment_id.pay_id

    def get_destination(self, payment_id: PaymentId):
        return PaymentIdGatewaySerializer(payment_id.gateway).data

    class Meta:
        model = PaymentId
        read_only_fields = fields = ('pay_id', 'verified', 'destination')


class AuthorizationIdViewsSet(ModelViewSet):
    serializer_class = AuthorizationIdSerializer

    def get_object(self):
        gateway = PaymentIdGateway.live_objects.first()
        return get_object_or_404(PaymentId, user=self.request.user, gateway=gateway, deleted=False)
