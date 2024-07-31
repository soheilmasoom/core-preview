from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ModelViewSet

from accounts.models import User, FinotechRequest
from accounts.tasks import basic_verify_user
from accounts.utils.similarity import clean_persian_name
from analytics.utils.yandex import send_yandex_event
from financial.models.bank_card import BankCard, BankCardSerializer
from financial.validators import bank_card_pan_validator


class CardPanField(serializers.CharField):
    def to_representation(self, value):
        if value:
            return BankCardSerializer(instance=value).data

    def get_attribute(self, user: User):
        return user.bankcard_set.filter(kyc=True).order_by('id').last()


class BasicInfoSerializer(serializers.ModelSerializer):
    card_pan = CardPanField(validators=[bank_card_pan_validator])
    reason = serializers.SerializerMethodField()

    def get_reason(self, user: User):
        if user.verify_status == User.REJECTED and user.level == User.LEVEL1:

            if user.reject_reason == User.NATIONAL_CODE_DUPLICATED:
                return 'کد ملی تکراری است. لطفا به پنل اصلی‌تان وارد شوید.'

            bank_card = user.bankcard_set.filter(kyc=True).first()
            if bank_card and bank_card.verified is False and bank_card.reject_reason == BankCard.DUPLICATED:
                return 'شماره کارت وارد شده تکراری است.'

            if not user.birth_date_verified:
                return 'کد ملی،‌ شماره کارت و تاریخ تولد متعلق به یک نفر نیستند.'

            if not user.first_name_verified or not user.last_name_verified:
                return 'نام و نام خانوادگی با دیگر اطلاعات مغایر است.'

    def get_kyc_bank_card(self, user: User, card_pan: str) -> BankCard:
        if BankCard.live_objects.filter(user=user, kyc=True, verified=True).exclude(card_pan=card_pan):
            raise ValidationError({'card_pan': 'امکان تغییر شماره کارت تایید شده وجود ندارد.'})

        bank_card = BankCard.live_objects.filter(user=user, kyc=True).first()

        if bank_card and bank_card.card_pan != card_pan:
            BankCard.live_objects.filter(user=user, card_pan=card_pan).update(deleted=True)

            bank_card.card_pan = card_pan
            bank_card.save()

        elif not bank_card:
            bank_card, _ = BankCard.live_objects.update_or_create(user=user, card_pan=card_pan, defaults={'kyc': True})

        return bank_card

    def update(self, user, validated_data):
        if user and user.verify_status in (User.PENDING, User.VERIFIED):
            raise ValidationError('امکان تغییر اطلاعات وجود ندارد.')

        if user.level > User.LEVEL1:
            raise ValidationError('کاربر تایید شده است.')

        if user.get_verify_weight() >= FinotechRequest.MAX_WEIGHT:
            raise ValidationError('به خاطر تلاش‌های مکرر امکان تایید خودکار وجود ندارد. برای ارتقای حساب با پشتیبانی صحبت کنید.')

        # if user.national_code_verified is False:
        #     raise ValidationError('کد ملی شما رد شده است. برای ارتقای حساب با پشتیبانی صحبت کنید.')

        date_delta = timezone.now().date() - validated_data['birth_date']
        age = date_delta.days / 365

        if age < 15:
            raise ValidationError('سن باید بالای ۱۵ سال باشد.')
        elif age > 120:
            raise ValidationError('تاریخ تولد نامعتبر است.')

        card_pan = validated_data.pop('card_pan')
        bank_card = self.get_kyc_bank_card(user, card_pan)

        if not bank_card.verified:
            bank_card.verified = None
            bank_card.save()

        to_update_user_fields = []

        if not user.national_code_verified:
            user.national_code = validated_data['national_code']
            user.national_code_verified = None
            to_update_user_fields.extend(['national_code', 'national_code_verified'])

        if not user.first_name_verified and validated_data.get('first_name'):
            user.first_name = clean_persian_name(validated_data['first_name'])
            user.first_name_verified = None
            to_update_user_fields.extend(['first_name', 'first_name_verified'])

        if not user.last_name_verified and validated_data.get('last_name'):
            user.last_name = clean_persian_name(validated_data['last_name'])
            user.last_name_verified = None
            to_update_user_fields.extend(['last_name', 'last_name_verified'])

        if not user.birth_date_verified:
            user.birth_date = validated_data['birth_date']
            user.birth_date_verified = None
            to_update_user_fields.extend(['birth_date', 'birth_date_verified'])

        user.save(update_fields=to_update_user_fields)
        user.change_status(User.PENDING)

        if User.objects.filter(level__gte=User.LEVEL2, national_code=user.national_code).exclude(id=user.id):
            user.national_code_verified = False
            user.save(update_fields=['national_code_verified'])
            user.change_status(User.REJECTED, User.NATIONAL_CODE_DUPLICATED)

            raise ValidationError('کد ملی تکراری است. لطفا به پنل اصلی‌تان وارد شوید.')

        if not settings.DEBUG_OR_TESTING_OR_STAGING:
            basic_verify_user.s(user.id).apply_async(countdown=60)

        send_yandex_event(user, 'try_basic_verify')

        return user

    class Meta:
        model = User
        fields = (
            'verify_status', 'level', 'first_name', 'last_name', 'birth_date', 'national_code', 'card_pan',
            'national_code_verified', 'first_name_verified', 'last_name_verified', 'birth_date_verified', 'reason'
        )
        read_only_fields = (
            'verify_status', 'level',
            'first_name_verified', 'last_name_verified', 'birth_date_verified'
        )
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'national_code': {'required': True},
            'birth_date': {'required': True},
        }


class BasicInfoVerificationViewSet(ModelViewSet):
    serializer_class = BasicInfoSerializer
    queryset = User.objects.all()

    def get_object(self):
        return self.request.user
