from django.conf import settings
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from django.db import transaction, IntegrityError
from django.utils import timezone

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
from accounts.models.phone_verification import VerificationCode


class SignupSerializer(serializers.Serializer):
    # Token is optional - either token OR authenticated user
    token = serializers.UUIDField(write_only=True, required=False)

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


class PhoneSignupView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        token = data.get('token')

        # Determine which flow: token-based or authenticated user
        if token:
            # Flow 1: Token provided (immediate signup after OTP)
            verification = VerificationCode.get_by_token(
                token,
                VerificationCode.SCOPE_PHONE_LOGIN
            )

            if not verification:
                raise ValidationError({'token': 'توکن نامعتبر است.'})

            if verification.token_used:
                raise ValidationError({'token': 'این توکن قبلا استفاده شده است.'})

            phone = verification.phone

            # Check if user exists
            if User.objects.filter(phone=phone).exists():
                raise ValidationError({'phone': 'شما قبلا در سیستم ثبت‌نام کرده‌اید. لطفا از قسمت ورود، وارد شوید.'})

            user = None
            is_new_user = True

        elif request.user.is_authenticated:
            # Flow 2: Authenticated user (skipped signup, now completing)
            user = request.user

            if user.level > User.LEVEL1:
                return Response({
                    'msg': 'شما قبلا اطلاعات خود را تکمیل کرده‌اید.',
                    'code': -1
                }, status=status.HTTP_400_BAD_REQUEST)

            verification = None
            is_new_user = False

        else:
            return Response({
                'msg': 'توکن یا احراز هویت الزامی است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        client_info = data.get('client_info')
        promotion = data.get('promotion', '')
        utm = data.get('utm') or {}

        try:
            with transaction.atomic():
                # Create or update user
                if is_new_user:
                    # Flow 1: Create new user
                    user, created = User.objects.get_or_create(
                        phone=phone,
                        defaults={'username': phone}
                    )

                    if not created:
                        # Race condition: user was created between check and get_or_create
                        raise ValidationError({'phone': 'شما قبلا در سیستم ثبت‌نام کرده‌اید.'})

                    account = Account.objects.create(user=user)
                else:
                    # Flow 2: Get existing account
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

                # Set referral if provided and not already set
                if data.get('referral_code') and not account.referred_by:
                    account.referred_by = Referral.objects.get(code=data['referral_code'])
                    account.save()

                    from gamify.utils import check_prize_achievements, Task
                    check_prize_achievements(account.referred_by.owner, Task.REFERRAL)

                if not settings.DEBUG_OR_TESTING_OR_STAGING:
                    basic_verify_user.s(user.id).apply_async(countdown=1)
                    send_yandex_event(user, 'try_basic_verify')

                # Mark verification token as used (Flow 1 only)
                if verification:
                    verification.set_token_used()

        except IntegrityError:
            return Response({
                'msg': 'خطایی در ثبت اطلاعات رخ داد. لطفا دوباره تلاش کنید.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        # These happen outside transaction
        create_traffic_source(request, user, utm)
        set_missions_to_user(user, promotion)
        send_yandex_event(user, 'sign_up', {'id': user.id})

        tokens = get_tokens_for_user(user)

        set_login_activity(
            request=request,
            user=user,
            client_info=client_info,
            refresh_token=tokens['refresh']
        )

        return Response(
            {
                'refresh': tokens['refresh'],
                'access': tokens['access'],
                'user': {'id': user.id}
            },
            status=status.HTTP_201_CREATED
        )