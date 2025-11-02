from django.conf import settings
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from django.db import transaction, IntegrityError
from django.utils import timezone
import logging

from accounts.models import User, Account, Referral
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.utils.login import set_login_activity
from accounts.utils.signup import create_traffic_source, set_missions_to_user
from accounts.utils.similarity import clean_persian_word
from rest_framework.response import Response
from accounts.views.phone_login import get_tokens_for_user
from analytics.utils.yandex import send_yandex_event
from financial.models import BankCard
from financial.validators import bank_card_pan_validator
from accounts.tasks import basic_verify_user

logger = logging.getLogger(__name__)


class SignupSerializer(serializers.Serializer):
    client_info = serializers.JSONField(required=False)

    # Optional KYC data
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    national_code = serializers.CharField(required=False)
    birth_date = serializers.DateField(required=False)
    card_pan = serializers.CharField(required=False, validators=[bank_card_pan_validator])

    # Additional data
    referral_code = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)

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


class PhoneSignupView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        # User must be authenticated (created in verify endpoint)
        if not request.user.is_authenticated:
            return Response({
                'msg': 'احراز هویت الزامی است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        user = request.user

        if user.level > User.LEVEL1:
            return Response({
                'msg': 'شما قبلا اطلاعات خود را تکمیل کرده‌اید.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        referral_code = (data.get('referral_code') or '').strip()

        try:
            with transaction.atomic():
                account = user.get_account()

                # Update user with KYC data (only if provided)
                if 'first_name' in data:
                    user.first_name = clean_persian_word(data.get('first_name', ''))
                    user.first_name_verified = None

                if 'last_name' in data:
                    user.last_name = clean_persian_word(data.get('last_name', ''))
                    user.last_name_verified = None

                if 'national_code' in data:
                    user.national_code = data.get('national_code')
                    user.national_code_verified = None

                if 'birth_date' in data:
                    user.birth_date = data.get('birth_date')
                    user.birth_date_verified = None

                user.save()

                if 'card_pan' in data:
                    BankCard.objects.create(
                        user=user,
                        card_pan=data['card_pan'],
                        kyc=True,
                        verified=None
                    )

                user.change_status(User.PENDING)

        except IntegrityError:
            return Response({
                'msg': 'خطایی در ثبت اطلاعات رخ داد. لطفا دوباره تلاش کنید.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set referral if provided and not already set - NON-BLOCKING
        if referral_code and not account.referred_by:
            try:
                referral = Referral.objects.filter(code=referral_code).first()
                if referral:
                    account.referred_by = referral
                    account.save(update_fields=['referred_by'])
                    logger.info(f'Set referral "{referral_code}" for user {user.id} from signup')

                    from gamify.utils import check_prize_achievements, Task
                    check_prize_achievements(account.referred_by.owner, Task.REFERRAL)
                else:
                    logger.warning(f'Invalid referral code: {referral_code}')
            except Exception as e:
                logger.warning(f'Failed to set referral for user {user.id}: {e}')

        if not settings.DEBUG_OR_TESTING_OR_STAGING:
            basic_verify_user.s(user.id).apply_async(countdown=1)
            send_yandex_event(user, 'try_basic_verify')

        return Response({
            'user': {'id': user.id},
            'message': 'اطلاعات شما با موفقیت ثبت شد.'
        })