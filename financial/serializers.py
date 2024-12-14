from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from financial.models import BankCard, BankAccount
from financial.utils.bank import get_bank_from_iban, get_bank_from_card_pan


class BankCardSerializer(serializers.ModelSerializer):
    info = serializers.SerializerMethodField()

    def get_info(self, bank_card: BankCard):
        bank = get_bank_from_card_pan(bank_card.card_pan)
        return bank and bank.as_dict()

    class Meta:
        model = BankCard
        fields = ('id', 'card_pan', 'verified', 'info')
        read_only_fields = ('verified', )

    def create(self, validated_data: dict):
        user = validated_data['user']
        card_pan = validated_data['card_pan']

        if BankCard.live_objects.filter(user=user, card_pan=card_pan).exists():
            raise ValidationError('این شماره کارت قبلا ثبت شده است.')

        bank_card = super().create(validated_data)

        from financial.tasks.verify import verify_bank_card_task
        verify_bank_card_task.delay(bank_card.id)

        return bank_card


class BankAccountSerializer(serializers.ModelSerializer):

    info = serializers.SerializerMethodField()

    def get_info(self, bank_account: BankAccount):
        bank = get_bank_from_iban(bank_account.iban)
        return bank and bank.as_dict()

    class Meta:
        model = BankAccount
        fields = ('id', 'iban', 'verified', 'info')
        read_only_fields = ('verified', )

    def create(self, validated_data: dict):
        user = validated_data['user']
        iban = validated_data['iban']

        if BankAccount.live_objects.filter(user=user, iban=iban).exists():
            raise ValidationError('این شماره شبا قبلا ثبت شده است.')

        old = BankAccount.objects.filter(user=user, iban=iban, deleted=True).order_by('id').last()

        if old:
            old.deleted = False
            old.save(update_fields=['deleted'])
            return old

        bank_account = super().create(validated_data)

        from financial.tasks.verify import verify_bank_account_task
        verify_bank_account_task.delay(bank_account.id)

        return bank_account
