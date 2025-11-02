from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction, IntegrityError
import logging

from accounts.models import User, Account, RefreshToken as RefreshTokenModel, Referral
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.validators import mobile_number_validator
from accounts.utils.login import set_login_activity
from accounts.utils.signup import create_traffic_source, set_missions_to_user
from analytics.utils.yandex import send_yandex_event

logger = logging.getLogger(__name__)


class PhoneLoginInitSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, validators=[mobile_number_validator])


class PhoneLoginInitView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        if request.user.is_authenticated:
            return Response({'msg': 'already logged in', 'code': 1})

        serializer = PhoneLoginInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']

        try:
            VerificationCode.send_otp_code(
                request=request,
                phone=phone,
                scope=VerificationCode.SCOPE_PHONE_LOGIN
            )
        except ValidationError as e:
            return Response({
                'msg': str(e),
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'msg': 'otp sent',
            'code': 0
        })


class PhoneLoginVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, validators=[mobile_number_validator])
    code = serializers.CharField(required=True)
    client_info = serializers.JSONField(required=False)
    promotion = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    referral_code = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    account, _ = Account.objects.get_or_create(user=user)
    refresh['account_id'] = account.id

    refresh_token_model, _ = RefreshTokenModel.objects.get_or_create(token=str(refresh))
    refresh['refresh_id'] = refresh_token_model.id

    refresh_token_model.token = str(refresh)
    refresh_token_model.save(update_fields=['token'])

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class PhoneLoginVerifyView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        serializer = PhoneLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']
        client_info = serializer.validated_data.get('client_info')
        promotion = (serializer.validated_data.get('promotion') or '').strip()
        utm = serializer.validated_data.get('utm') or {}
        referral_code = (serializer.validated_data.get('referral_code') or '').strip()

        otp_code = VerificationCode.get_by_code(
            code=code,
            phone=phone,
            scope=VerificationCode.SCOPE_PHONE_LOGIN
        )

        if not otp_code:
            return Response({
                'msg': 'کد پیامک نامعتبر است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(phone=phone).first()

        if user:
            # ===== EXISTING USER - JUST LOGIN =====
            otp_code.set_code_used()

            tokens = get_tokens_for_user(user)

            set_login_activity(
                request=request,
                user=user,
                client_info=client_info,
                refresh_token=tokens['refresh']
            )

            return Response({
                **tokens,
                'is_registered': True,
                'user': {'id': user.id}
            })
        else:
            # ===== NEW USER - CREATE USER HERE AND SET PROMOTION/REFERRAL =====
            otp_code.set_code_used()

            try:
                with transaction.atomic():
                    # Create new user
                    user, created = User.objects.get_or_create(
                        phone=phone,
                        defaults={'username': phone}
                    )

                    if not created:
                        # Race condition
                        raise ValidationError({'phone': 'شما قبلا در سیستم ثبت‌نام کرده‌اید.'})

                    account = Account.objects.create(user=user)

            except IntegrityError:
                return Response({
                    'msg': 'شما قبلا در سیستم ثبت‌نام کرده‌اید.',
                    'code': -1
                }, status=status.HTTP_400_BAD_REQUEST)

            # Non-blocking operations - set promotion/referral/utm for NEW user

            # Set referral if provided
            if referral_code:
                try:
                    referral = Referral.objects.filter(code=referral_code).first()
                    if referral:
                        account.referred_by = referral
                        account.save(update_fields=['referred_by'])
                        logger.info(f'Set referral "{referral_code}" for new user {user.id}')

                        from gamify.utils import check_prize_achievements, Task
                        check_prize_achievements(account.referred_by.owner, Task.REFERRAL)
                    else:
                        logger.warning(f'Invalid referral code: {referral_code}')
                except Exception as e:
                    logger.warning(f'Failed to set referral for user {user.id}: {e}')

            # Create traffic source
            try:
                create_traffic_source(request, user, utm)
            except Exception as e:
                logger.warning(f'Failed to create traffic source for user {user.id}: {e}')

            # Set mission journey (promotion)
            if promotion:
                try:
                    set_missions_to_user(user, promotion)
                    logger.info(f'Set promotion "{promotion}" for new user {user.id}')
                except Exception as e:
                    logger.warning(f'Failed to set promotion for user {user.id}: {e}')

            # Send signup event
            try:
                send_yandex_event(user, 'sign_up', {'id': user.id})
            except Exception as e:
                logger.warning(f'Failed to send yandex event for user {user.id}: {e}')

            # Get tokens
            tokens = get_tokens_for_user(user)

            set_login_activity(
                request=request,
                user=user,
                client_info=client_info,
                refresh_token=tokens['refresh'],
                is_sign_up=True
            )

            return Response({
                **tokens,
                'is_registered': False,  # First time user
                'user': {'id': user.id}
            })