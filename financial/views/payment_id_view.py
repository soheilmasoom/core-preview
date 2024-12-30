from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from financial.models import PaymentId, PayIdGateway, BankAccount
from financial.utils.bank import get_bank_from_slug
from financial.utils.payment_id_client import get_payment_id_client


class PayIdGatewaySerializer(serializers.ModelSerializer):
    bank = serializers.SerializerMethodField()

    def get_bank(self, general_bank: PayIdGateway):
        bank = get_bank_from_slug(general_bank.bank)
        return bank.as_dict()

    class Meta:
        model = PayIdGateway
        fields = ('iban', 'name', 'bank', 'deposit_address')


class PaymentIdSerializer(serializers.ModelSerializer):
    pay_id = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()

    def create(self, validated_data):
        user = self.context['request'].user

        if user.level <= User.LEVEL1:
            raise ValidationError({'user': 'ابتدا احراز هویت کنید.'})

        if not BankAccount.objects.filter(user=user, verified=True, deleted=False):
            raise ValidationError({'iban': 'شما باید حداقل یک حساب بانکی تایید شده داشته باشید.'})

        gateway = PayIdGateway.live_objects.filter(type=PayIdGateway.JIBIT_OLD).first()

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
        return PayIdGatewaySerializer(payment_id.gateway).data

    class Meta:
        model = PaymentId
        read_only_fields = fields = ('pay_id', 'verified', 'destination')


class PaymentIdViewsSet(ModelViewSet):
    serializer_class = PaymentIdSerializer

    def get_object(self):
        gateway = PayIdGateway.live_objects.filter(type=PayIdGateway.JIBIT_OLD).first()
        return get_object_or_404(PaymentId, user=self.request.user, gateway=gateway, deleted=False)
