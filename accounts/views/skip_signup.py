from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction, IntegrityError
import logging

from accounts.models import User, Account
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.views.phone_login import get_tokens_for_user
from accounts.utils.login import set_login_activity
from accounts.utils.signup import create_traffic_source, set_missions_to_user

logger = logging.getLogger(__name__)


class SkipSignupSerializer(serializers.Serializer):
    token = serializers.UUIDField(required=True)
    client_info = serializers.JSONField(required=False)
    promotion = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)


class SkipSignupView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        serializer = SkipSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        client_info = serializer.validated_data.get('client_info')
        promotion = (serializer.validated_data.get('promotion') or '').strip()
        utm = serializer.validated_data.get('utm') or {}

        verification = VerificationCode.get_by_token(
            token,
            VerificationCode.SCOPE_PHONE_LOGIN
        )

        if not verification:
            return Response({
                'msg': 'توکن نامعتبر است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        if verification.token_used:
            return Response({
                'msg': 'این توکن قبلا استفاده شده است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        phone = verification.phone

        try:
            with transaction.atomic():
                # Use get_or_create to handle race conditions
                user, created = User.objects.get_or_create(
                    phone=phone,
                    defaults={'username': phone}
                )

                if not created:
                    return Response({
                        'msg': 'شما قبلا در سیستم ثبت‌نام کرده‌اید.',
                        'code': -1
                    }, status=status.HTTP_400_BAD_REQUEST)

                Account.objects.create(user=user)
                verification.set_token_used()
        except IntegrityError:
            return Response({
                'msg': 'شما قبلا در سیستم ثبت‌نام کرده‌اید.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        # Non-blocking operations
        try:
            create_traffic_source(request, user, utm)
        except Exception as e:
            logger.warning(f'Failed to create traffic source for user {user.id}: {e}')

        if promotion:
            try:
                set_missions_to_user(user, promotion)
            except Exception as e:
                logger.warning(f'Failed to set missions for user {user.id}: {e}')

        tokens = get_tokens_for_user(user)

        set_login_activity(
            request=request,
            user=user,
            client_info=client_info,
            refresh_token=tokens['refresh']
        )

        return Response({
            **tokens,
            'user': {'id': user.id},
            'message': 'حساب شما ایجاد شد. برای معامله، اطلاعات خود را تکمیل کنید.'
        }, status=status.HTTP_201_CREATED)