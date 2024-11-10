import logging
import uuid
from datetime import timedelta
from typing import Union

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F
from django.utils import timezone
from decouple import config
from rest_framework.exceptions import ValidationError

from accounts.models import SpamPhone, User
from accounts.utils.ip import get_client_ip
from accounts.utils.validation import generate_random_code, PHONE_MAX_LENGTH, fifteen_minutes_later_datetime, MINUTES, \
    persian_timedelta

logger = logging.getLogger(__name__)


class VerificationCode(models.Model):
    MAX_MISSED_CHECK_PER_OTP = 5

    MAX_ALLOWED_MISSED_CHECKS = {
        timedelta(hours=1): 10,
        timedelta(days=1): 50,
    }

    EXPIRATION_TIME = 15 * MINUTES

    SCOPE_FORGET_PASSWORD = 'forget'
    SCOPE_VERIFY_PHONE = 'verify'
    SCOPE_VERIFY_PHONE_WIDGET = 'verify_widget'

    SCOPE_VERIFY_EMAIL = 'email_verify'
    SCOPE_CRYPTO_WITHDRAW = 'withdraw'
    SCOPE_FIAT_WITHDRAW = 'fiat_withdraw'
    SCOPE_TELEPHONE = 'tel'
    SCOPE_CHANGE_PASSWORD = 'change_pass'
    SCOPE_CHANGE_PHONE = 'change_phone'
    SCOPE_CHANGE_PHONE_INIT = 'change_phone_init'
    SCOPE_NEW_PHONE = 'new_phone'
    SCOPE_2FA = '2fa'
    SCOPE_FORGET_2FA = 'forget_2fa'
    SCOPE_API_TOKEN = 'api_token'
    SCOPE_ADDRESS_BOOK = 'address_book'

    SCOPES = SCOPE_FORGET_PASSWORD, SCOPE_VERIFY_PHONE, SCOPE_VERIFY_PHONE_WIDGET, SCOPE_CRYPTO_WITHDRAW, \
             SCOPE_TELEPHONE, SCOPE_CHANGE_PASSWORD, SCOPE_CHANGE_PHONE, SCOPE_CHANGE_PHONE_INIT, SCOPE_VERIFY_EMAIL, \
             SCOPE_FIAT_WITHDRAW, SCOPE_2FA, SCOPE_API_TOKEN, SCOPE_ADDRESS_BOOK, SCOPE_NEW_PHONE, SCOPE_FORGET_2FA,

    RESTRICTED_SEND_SCOPES = [SCOPE_NEW_PHONE, SCOPE_FORGET_2FA]
    RESTRICTED_VERIFY_SCOPES = [SCOPE_CHANGE_PHONE_INIT]

    NO_USER_SCOPES = [SCOPE_VERIFY_PHONE, SCOPE_VERIFY_PHONE_WIDGET]

    created = models.DateTimeField(auto_now_add=True)
    expiration = models.DateTimeField(default=fifteen_minutes_later_datetime)

    phone = models.CharField(
        max_length=PHONE_MAX_LENGTH,
        verbose_name='شماره تماس',
        db_index=True
    )

    code = models.CharField(
        max_length=6,
        db_index=True,
        validators=[RegexValidator(r'^\d{4,6}$')]
    )

    code_used = models.BooleanField(
        default=False,
    )

    token_used = models.BooleanField(
        default=False,
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
    )

    scope = models.CharField(
        max_length=32,
        choices=[(s, s) for s in SCOPES],
        db_index=True
    )

    user = models.ForeignKey(
        to='accounts.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    user_agent = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True)

    missed_checks = models.PositiveSmallIntegerField(default=0)

    @classmethod
    def get_by_code(cls, code: str, phone: str, scope: str, user=None) -> 'VerificationCode':
        otp_codes = VerificationCode.objects.filter(
            code_used=False,
            expiration__gt=timezone.now(),
            scope=scope,
            phone=phone
        )

        if user:
            otp_codes = otp_codes.filter(user=user)

        otp = otp_codes.filter(
            code=code,
            missed_checks__lte=cls.MAX_MISSED_CHECK_PER_OTP
        ).order_by('created').last()

        if not otp:
            missed_count = otp_codes.update(missed_checks=F('missed_checks') + 1)

            if missed_count:
                if user and not user.ban_sms_otp_until:  # todo: handle signup throttle policies
                    cls._check_if_should_ban_user(user)

        return otp

    @classmethod
    def get_by_token(cls, token: str, scope: str) -> 'VerificationCode':
        return VerificationCode.objects.filter(
            token=token,
            token_used=False,
            created__gte=timezone.now() - timedelta(hours=1),
            scope=scope,
        ).first()

    @classmethod
    def _log_ignore_reason(cls, reason):
        logger.info(f'Ignored sending otp due to {reason}')

    @classmethod
    def should_throttle(cls, request, phone: str, scope: str, user: User = None):
        # todo: handle throttling (don't allow to send more than twice in minute per phone / scope)
        # todo: use user devices / ip , ...

        user_agent = request.META.get('HTTP_USER_AGENT', '')

        now = timezone.now()

        if SpamPhone.objects.filter(phone=phone):
            cls._log_ignore_reason('spam phone')
            return True

        if user_agent == 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36':
            cls._log_ignore_reason('user agent blacklist')
            return True

        if user and user.ban_sms_otp_until and user.ban_sms_otp_until > now:
            td = persian_timedelta(user.ban_sms_otp_until - now)
            raise ValidationError(f'امکان درخواست پیامک تا {td} دیگر وجود ندارد.')

        any_recent_code = VerificationCode.objects.filter(
            phone=phone,
            scope=scope,
            created__gte=timezone.now() - timedelta(minutes=1),
        ).count() >= 2

        if any_recent_code:
            cls._log_ignore_reason('recent sends')
            return True

        prev_codes = VerificationCode.objects.filter(
            phone=phone,
            scope=scope,
            created__gte=timezone.now() - timedelta(minutes=5),
        ).count()

        if prev_codes >= 5:
            cls._log_ignore_reason('multiple prev sends')
            return True

        if user:
            prev_codes = VerificationCode.objects.filter(
                user=user,
                created__gte=timezone.now() - timedelta(minutes=15),
            ).count()

            if prev_codes >= 10:
                cls._log_ignore_reason('user too much sent otps')
                return True

        return False

    @classmethod
    def _check_if_should_ban_user(cls, user: user):
        codes = VerificationCode.objects.filter(
            user=user,
            missed_checks__gt=cls.MAX_MISSED_CHECK_PER_OTP
        )

        now = timezone.now()

        for delta, max_misses in sorted(cls.MAX_ALLOWED_MISSED_CHECKS.items(), key=lambda s: s[0], reverse=True):
            missed_count = codes.filter(created__gte=now - delta).count()
            if missed_count >= max_misses:
                user.ban_sms_otp_until = now + delta
                user.save(update_fields=['ban_sms_otp_until'])

    @classmethod
    def send_otp_code(cls, request, phone: str, scope: str, user: User = None) -> Union['VerificationCode', None]:
        assert user or scope in cls.NO_USER_SCOPES

        if cls.should_throttle(request=request, phone=phone, scope=scope, user=user):
            return

        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        if scope in cls.NO_USER_SCOPES:
            code_length = 4
        else:
            code_length = 6

        if settings.GENERATE_FAKE_OTP:
            code = '1' * code_length
        else:
            code = generate_random_code(code_length)

        otp_code = VerificationCode.objects.create(
            phone=phone,
            scope=scope,
            code=code,
            user=user,
            ip=ip,
            user_agent=user_agent
        )

        if config('OTP_BY_SMS_IR', cast=bool, default=False):
            from accounts.tasks import send_message_by_sms_ir
            send_message_by_sms_ir(
                phone=phone,
                template='69129',
                params={
                    'brand': settings.BRAND,
                    'code': otp_code.code
                }
            )
        else:
            from accounts.tasks import send_message_by_kavenegar
            send_message_by_kavenegar(
                phone=otp_code.phone,
                token=otp_code.code,
                template='verify'
            )

        return otp_code

    def set_code_used(self):
        self.code_used = True
        self.save()

    def set_token_used(self):
        self.token_used = True
        self.save()
