from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from financial.models.bank_card import BankAccountSerializer, BankAccount


class BankAccountView(ModelViewSet):
    serializer_class = BankAccountSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['verified']

    def get_queryset(self):
        return BankAccount.live_objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        if self.request.user.level < User.LEVEL2:
            raise ValidationError('برای افزودن شماره شبا ابتدا احراز هویت کنید.')

        serializer.save(user=self.request.user)

    def perform_destroy(self, bank_account: BankAccount):
        if bank_account.verified is None:
            raise ValidationError('شماره شبا در حال اعتبارسنجی است.')

        if BankAccount.live_objects.filter(user=bank_account.user).exclude(id=bank_account.id).count() == 0:
            raise ValidationError('برای حذف این شماره شبا، ابتدا یک شماره شبای جدید وارد کنید.')

        if bank_account.verified and BankAccount.live_objects.filter(user=bank_account.user, verified=True).count() == 1:
            raise ValidationError('شما باید حداقل یک شماره شبا تایید شده داشته باشید.')

        bank_account.deleted = True
        bank_account.save()
