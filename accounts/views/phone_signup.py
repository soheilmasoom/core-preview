from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from django.db import transaction
from django.utils import timezone

from accounts.models import User, Account, UserAuthRequest, Referral
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.utils.login import set_login_activity
from accounts.utils.signup import create_traffic_source, set_missions_to_user
from accounts.utils.similarity import clean_persian_word
from accounts.views.phone_login import get_tokens_for_user
from analytics.utils.yandex import send_yandex_event
from financial.models import BankCard
from financial.validators import bank_card_pan_validator
from accounts.tasks import basic_verify_user


class SignupSerializer(serializers.Serializer):
    # Verification
    token = serializers.UUIDField(write_only=True, required=True)

    client_info = serializers.JSONField(required=False)
    # Optional KYC data
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    national_code = serializers.CharField(required=False)
    birth_date = serializers.DateField(required=False)
    card_pan = serializers.CharField(required=False, validators=[bank_card_pan_validator])

    # Additional data
    referral_code = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    promotion = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)

    @staticmethod
    def validate_referral_code(code):
        if code and not Referral.objects.filter(code=code).exists():
            raise ValidationError('کد معرف نامعتبر است.')
        return code

    def validate(self, data):
        kyc_fields = {'national_code', 'birth_date', 'card_pan', 'first_name', 'last_name'}
        required_kyc_fields = {'national_code', 'birth_date', 'card_pan'}

        provided_kyc_fields = set(data.keys()) & kyc_fields

        if provided_kyc_fields:
            missing_required = required_kyc_fields - provided_kyc_fields
            if missing_required:
                field_names = {
                    'national_code': 'کد ملی',
                    'birth_date': 'تاریخ تولد',
                    'card_pan': 'شماره کارت'
                }
                missing_fields = [field_names[field] for field in missing_required]
                raise ValidationError(f'برای احراز هویت، {", ".join(missing_fields)} الزامی است.')

            if 'birth_date' in data:
                date_delta = timezone.now().date() - data['birth_date']
                age = date_delta.days / 365
                if age < 15:
                    raise ValidationError('سن باید بالای ۱۵ سال باشد.')
                elif age > 120:
                    raise ValidationError('تاریخ تولد نامعتبر است.')

        return data

    def create(self, validated_data):
        token = validated_data.pop('token')
        client_info = validated_data.pop('client_info', None)
        verification = VerificationCode.get_by_token(token, VerificationCode.SCOPE_PHONE_LOGIN)

        if not verification:
            raise ValidationError({'token': 'توکن نامعتبر است.'})

        if verification.token_used:
            raise ValidationError({'token': 'این توکن قبلا استفاده شده است.'})

        phone = verification.phone
        if User.objects.filter(phone=phone).exists():
            raise ValidationError({'phone': 'شما قبلا در سیستم ثبت‌نام کرده‌اید. لطفا از قسمت ورود، وارد شوید.'})

        promotion = validated_data.get('promotion', '')
        utm = validated_data.get('utm', {})

        with transaction.atomic():
            user = User.objects.create_user(
                username=phone,
                phone=phone,
            )

            account = Account.objects.create(user=user)

            if validated_data.get('referral_code'):
                account.referred_by = Referral.objects.get(code=validated_data['referral_code'])
                account.save()

                from gamify.utils import check_prize_achievements, Task
                check_prize_achievements(account.referred_by.owner, Task.REFERRAL)

            kyc_fields = {'national_code', 'birth_date', 'card_pan', 'first_name', 'last_name'}
            if any(field in validated_data for field in kyc_fields):
                user.first_name = clean_persian_word(validated_data.get('first_name', ''))
                user.last_name = clean_persian_word(validated_data.get('last_name', ''))
                user.national_code = validated_data.get('national_code')
                user.birth_date = validated_data.get('birth_date')

                if user.national_code:
                    user.national_code_verified = None
                if user.first_name:
                    user.first_name_verified = None
                if user.last_name:
                    user.last_name_verified = None
                if user.birth_date:
                    user.birth_date_verified = None

                user.save()

                if 'card_pan' in validated_data:
                    BankCard.objects.create(
                        user=user,
                        card_pan=validated_data['card_pan'],
                        kyc=True,
                        verified=None
                    )

                user.change_status(User.PENDING)

                if not settings.DEBUG_OR_TESTING_OR_STAGING:
                    basic_verify_user.s(user.id).apply_async(countdown=1)
                    send_yandex_event(user, 'try_basic_verify')

        verification.set_token_used()
        create_traffic_source(self.context['request'], user, utm)

        set_missions_to_user(user, promotion)

        send_yandex_event(user, 'sign_up', {'id': user.id})

        tokens = get_tokens_for_user(user)

        set_login_activity(
                request=self.context['request'],
                user=user,
                client_info=client_info,
                refresh_token=tokens['refresh']
            )
        return {
            'user': user,
            **tokens
        }


class PhoneSignupView(CreateAPIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    serializer_class = SignupSerializer