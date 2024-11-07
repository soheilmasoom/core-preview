import random
import string
import uuid
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Union
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_otp.plugins.otp_totp.models import TOTPDevice
from simple_history.models import HistoricalRecords

from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.models import Notification, Account, SystemConfig
from accounts.models.user_feature_perm import UserFeaturePerm
from accounts.utils.mask import get_masked_phone
from accounts.utils.telegram import send_support_message
from accounts.utils.validation import PHONE_MAX_LENGTH
from accounts.validators import mobile_number_validator, national_card_code_validator, telephone_number_validator
from analytics.event.producer import get_kafka_producer
from analytics.utils.dto import UserEvent
from ledger.utils.fields import DONE


class CustomUserManager(UserManager):
    def create_superuser(self, email=None, password=None, **extra_fields):
        return super(CustomUserManager, self).create_superuser(extra_fields['phone'], email, password, **extra_fields)


class UserType(Enum):
    CORPORATION = 'corporation'
    PERSONAL = 'personal'


class User(AbstractUser):
    LEVEL1 = 1
    LEVEL2 = 2
    LEVEL3 = 3
    LEVEL4 = 4

    INIT, PENDING, REJECTED, VERIFIED = 'init', 'pending', 'rejected', 'verified'

    USERNAME_FIELD = 'phone'

    FIAT, CRYPTO = 'fiat', 'crypto'

    NATIONAL_CODE_DUPLICATED = 'duplicated-national-code'

    objects = CustomUserManager()
    history = HistoricalRecords()

    chat_uuid = models.UUIDField(default=uuid4)

    phone = models.CharField(
        max_length=PHONE_MAX_LENGTH,
        validators=[mobile_number_validator],
        verbose_name='شماره موبایل',
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        error_messages={
            'unique': 'شماره موبایل وارد شده از قبل در سیستم موجود است.'
        }
    )

    first_name_verified = models.BooleanField(null=True, blank=True, verbose_name='تاییدیه نام', )
    last_name_verified = models.BooleanField(null=True, blank=True, verbose_name='تاییدیه نام خانوادگی', )

    national_code = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='کد ملی',
        db_index=True,
        validators=[national_card_code_validator],
    )
    national_code_verified = models.BooleanField(null=True, blank=True, verbose_name='تاییدیه کد ملی', )
    national_code_phone_verified = models.BooleanField(null=True, blank=True,
                                                       verbose_name='تاییدیه کد ملی و موبایل (شاهکار)', )

    birth_date = models.DateField(null=True, blank=True, verbose_name='تاریخ تولد', )
    birth_date_verified = models.BooleanField(null=True, blank=True, verbose_name='تاییدیه تاریخ تولد', )

    level_2_verify_datetime = models.DateTimeField(blank=True, null=True, verbose_name='تاریخ تایید سطح ۲')
    level_3_verify_datetime = models.DateTimeField(blank=True, null=True, verbose_name='تاریخ تایید سطح 3')

    level = models.PositiveSmallIntegerField(
        default=LEVEL1,
        choices=(
            (LEVEL1, 'level 1'), (LEVEL2, 'level 2'), (LEVEL3, 'level 3'), (LEVEL4, 'level 4'),
        ),
        verbose_name='سطح',
        db_index=True
    )

    verify_status = models.CharField(
        max_length=8,
        choices=((INIT, INIT), (PENDING, PENDING), (REJECTED, REJECTED), (VERIFIED, VERIFIED)),
        default=INIT,
        verbose_name='وضعیت تایید'
    )

    reject_reason = models.CharField(
        max_length=32,
        blank=True,
        choices=((NATIONAL_CODE_DUPLICATED, NATIONAL_CODE_DUPLICATED),)
    )

    first_fiat_deposit_date = models.DateTimeField(blank=True, null=True, verbose_name='زمان اولین واریز ریالی')
    first_crypto_deposit_date = models.DateTimeField(blank=True, null=True, verbose_name='زمان اولین واریز رمزارزی')

    selfie_image = models.OneToOneField(
        to='multimedia.Image',
        on_delete=models.PROTECT,
        verbose_name='عکس سلفی',
        related_name='+',
        blank=True,
        null=True
    )
    telephone = models.CharField(
        max_length=PHONE_MAX_LENGTH,
        validators=[telephone_number_validator],
        verbose_name='شماره تلفن',
        blank=True,
        null=True,
        db_index=True,
    )

    telephone_verified = models.BooleanField(null=True, blank=True, verbose_name='تاییدیه شماره تلفن')

    selfie_image_verified = models.BooleanField(null=True, blank=True, verbose_name='تاییدیه عکس سلفی')
    verifier = models.ForeignKey(
        to='accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='تایید کننده عکس سلفی'
    )

    archived = models.BooleanField(
        db_index=True,
        default=False,
        verbose_name='بایگانی'
    )

    margin_quiz_pass_date = models.DateTimeField(null=True, blank=True)

    show_margin = models.BooleanField(default=False, verbose_name='امکان مشاهده حساب تعهدی')
    show_strategy_bot = models.BooleanField(default=True, verbose_name='امکان مشاهده ربات')
    show_community = models.BooleanField(default=False, verbose_name='امکان مشاهده کامیونیتی')
    show_staking = models.BooleanField(default=True, verbose_name='امکان مشاهده سرمایه‌گذاری')

    selfie_image_discard_text = models.TextField(blank=True, verbose_name='توضیحات رد کردن عکس سلفی')

    can_withdraw = models.BooleanField(default=True)
    can_withdraw_crypto = models.BooleanField(default=True)
    can_trade = models.BooleanField(default=True)

    withdraw_limit_whitelist = models.BooleanField(default=False)
    withdraw_risk_level_multiplier = models.PositiveIntegerField(
        default=1,
        choices=((1, 1), (2, 2), (3, 3), (5, 5), (10, 10), (20, 20), (40, 40))
    )

    mission_journey = models.ForeignKey('gamify.MissionJourney', null=True, blank=True, on_delete=models.SET_NULL)

    custom_crypto_withdraw_ceil = models.PositiveBigIntegerField(null=True, blank=True)
    custom_fiat_withdraw_ceil = models.PositiveBigIntegerField(null=True, blank=True)

    is_price_notif_on = models.BooleanField(default=False)

    suspended_until = models.DateTimeField(null=True, blank=True, verbose_name='زمان تعلیق شدن کاربر')
    suspension_reason = models.CharField(max_length=128, blank=True, null=True)

    ban_deposit_with_credit_bank_cards = models.BooleanField(default=False)

    telegram_bot_enabled = models.BooleanField(default=False)

    def __str__(self):
        name = get_masked_phone(self.username)

        if self.get_full_name():
            name += ' ' + self.get_full_name()

        return name

    @property
    def registration_type(self):
        if self.company is None:
            return UserType.PERSONAL
        else:
            return UserType.CORPORATION

    def is_2fa_active(self):
        return TOTPDevice.objects.filter(user=self, confirmed=True).exists()

    def is_2fa_valid(self, totp: str):
        if not self.is_2fa_active():
            return True

        device = TOTPDevice.objects.filter(user=self, confirmed=True).first()
        return device.verify_token(totp)

    def archive_registered_phone(self):
        account = self.get_account()

        errors = []
        if self.level == User.LEVEL1:
            if account.has_zero_balance():
                self.username = self.username + "#" + ''.join(random.choices(string.ascii_lowercase, k=4))
                self.phone = None
                self.save(update_fields=['phone', 'username'])
            else:
                errors.append("موجودی کاربر صفر نیست")
        else:
            errors.append("کاربر سطح یک نیست")
        if errors:
            raise ValidationError(errors)

    def get_account(self) -> Account:
        if not self.id or self.is_anonymous:
            return Account(user=self)

        account, _ = Account.objects.get_or_create(user=self)
        return account

    def suspend(self, duration: timedelta, reason: str = None):
        suspended_until = duration + timezone.now()
        past_suspension = self.suspended_until
        if not past_suspension:
            self.suspended_until = suspended_until
        else:
            self.suspended_until = max(past_suspension, suspended_until)

        if reason and past_suspension != self.suspended_until:
            self.suspension_reason = reason
            self.save(update_fields=['suspended_until', 'suspension_reason'])
            self.send_suspension_message(reason, duration)

    def send_suspension_message(self, reason: str, duration: timedelta):
        from accounts.tasks.send_sms import send_kavenegar_exclusive_sms
        from django.template import loader
        duration = 'یک‌ روز' if duration == timedelta(days=1) else 'یک‌ ساعت'
        context = {
            'reason': reason,
            'brand': settings.BRAND,
            'duration': duration
        }
        content = loader.render_to_string('accounts/notif/sms/user_suspended_message.txt', context=context)
        Notification.send(
            recipient=self,
            title='محدودیت برداشت',
            message=f'برداشت‌های رمزارزی شما به دلیل {reason} تا {duration} آینده محدود شده است.',
        )
        send_kavenegar_exclusive_sms(self.phone, content=content)

    @property
    def is_suspended(self):
        if not self.suspended_until:
            return False
        return timezone.now() <= self.suspended_until

    @property
    def kyc_bank_card(self):
        return self.bankcard_set.filter(kyc=True).first()

    def get_verify_weight(self) -> int:
        from accounts.models import UserAuthRequest
        return UserAuthRequest.objects.filter(
            user=self,
            search_key__isnull=False
        ).exclude(search_key='').aggregate(w=Sum('weight'))['w'] or 0

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

        # constraints = [
        #     UniqueConstraint(
        #         fields=["national_code"],
        #         name="unique_verified_national_code",
        #         condition=Q(level__gt=1),
        #     )
        # ]

        permissions = [
            ("can_generate_notification", "Can Generate All Kind Of Notification"),
            ("manage_users", "Manage Users Info"),
            ("list_user", "Can list user"),
            ("can_view_user_selfie", "Can view user selfie"),
        ]

    def change_status(self, status: str, reason: str = ''):
        from accounts.tasks.verify_user import alert_user_verify_status

        if self.verify_status != self.VERIFIED and status == self.VERIFIED:
            self.verify_status = self.INIT

            if self.level == User.LEVEL1:
                if User.objects.filter(level__gte=User.LEVEL2, national_code=self.national_code).exclude(id=self.id):
                    self.national_code_verified = False
                    self.save(update_fields=['verify_status', 'national_code_verified'])
                    return self.change_status(User.REJECTED, User.NATIONAL_CODE_DUPLICATED)

            self.level += 1
            with transaction.atomic():
                if self.level == User.LEVEL2:
                    self.level_2_verify_datetime = timezone.now()

                elif self.level == User.LEVEL3:
                    self.level_3_verify_datetime = timezone.now()

                self.archived = False
                self.save(update_fields=['verify_status', 'level', 'level_2_verify_datetime', 'level_3_verify_datetime',
                                         'archived'])

            if self.level == User.LEVEL2:
                from gamify.utils import check_prize_achievements, Task
                check_prize_achievements(self.account, Task.VERIFY_LEVEL2)

            alert_user_verify_status(self)

        elif self.verify_status != self.REJECTED and status == self.REJECTED:
            if self.level == self.LEVEL1:
                link = url_to_edit_object(self)
                send_support_message(
                    message='اطلاعات سطح %d کاربر مورد تایید قرار نگرفت. لطفا دستی بررسی شود.' % (self.level + 1),
                    link=link
                )

            self.verify_status = status
            self.reject_reason = reason
            self.save(update_fields=['verify_status', 'reject_reason'])

            alert_user_verify_status(self)

        else:
            self.verify_status = status
            self.archived = False
            self.save(update_fields=['verify_status', 'archived'])

    @property
    def primary_data_verified(self) -> bool:
        return self.first_name and self.first_name_verified and self.last_name and self.last_name_verified \
            and self.birth_date and self.birth_date_verified

    def get_level2_verify_fields(self):
        from financial.models import BankCard

        bank_card_verified = None

        if BankCard.live_objects.filter(user=self, verified=True):
            bank_card_verified = True
        elif not BankCard.live_objects.filter(user=self, verified__isnull=True):
            bank_card_verified = False

        return [
            bool(self.national_code),
            bool(self.birth_date), self.birth_date_verified,
            bool(self.first_name), self.first_name_verified,
            bool(self.last_name), self.last_name_verified,
            bank_card_verified
        ]

    def verify_level2_if_not(self) -> bool:
        if self.level == User.LEVEL1 and all(self.get_level2_verify_fields()):
            self.change_status(User.VERIFIED)

            return True

        return False

    def reject_level2_if_should(self) -> bool:

        if self.level == User.LEVEL1 and self.verify_status == self.PENDING:
            level2_fields = self.get_level2_verify_fields()
            any_none = list(filter(lambda f: f is None, level2_fields))

            if not all(level2_fields) and not any_none:
                self.change_status(User.REJECTED)
                return True

        return False

    @classmethod
    def get_user_from_login(cls, email_or_phone: str) -> 'User':
        return User.objects.filter(Q(phone=email_or_phone) | Q(email=email_or_phone)).first()

    def save(self, *args, **kwargs):
        old = self.id and User.objects.get(id=self.id)
        super(User, self).save(*args, **kwargs)

        from accounts.models import LoginActivity
        if old and old.password != self.password:
            for login_activity in (LoginActivity.objects.filter(user=self)  # todo: maybe error prone
                    .exclude(refresh_token__isnull=True, session__isnull=True)):
                login_activity.destroy()

        if self.level == self.LEVEL2 and self.verify_status == self.PENDING:
            if self.national_code_phone_verified and self.selfie_image_verified:
                self.change_status(self.VERIFIED)
            else:
                fields = [self.selfie_image_verified]
                any_false = any(map(lambda f: f is False, fields))

                if any_false:
                    self.change_status(self.REJECTED)

        elif self.level == self.LEVEL1 and self.verify_status == self.PENDING:
            self.reject_level2_if_should()
            self.verify_level2_if_not()

        if old and old.selfie_image_verified is None and self.selfie_image_verified is False:
            Notification.send(
                recipient=self,
                title='عکس سلفی شما تایید نشد',
                level=Notification.ERROR,
                message=self.selfie_image_discard_text
            )
            self.selfie_image_discard_text = ''
            super(User, self).save(*args, **kwargs)

    def has_feature_perm(self, feature: str):
        return self.userfeatureperm_set.filter(feature=feature).exists()

    def get_feature_limit(self, name: str) -> Union[Decimal, None]:
        user_feature = self.userfeatureperm_set.filter(feature=name).first()

        if user_feature:
            return user_feature.limit
        else:
            return UserFeaturePerm.DEFAULT_LIMITS.get(name)

    def get_legal_name(self):
        company = getattr(self, 'company', None)

        if company:
            return company.name
        else:
            return self.get_full_name()

    def get_fiat_deposits(self) -> int:
        from financial.models import Payment

        return Payment.objects.filter(user=self, status=DONE).aggregate(s=Sum('amount'))['s'] or 0

    def is_margin_active(self) -> bool:
        if SystemConfig.get_system_config().show_margin:
            return True

        return self.show_margin

    def ban_deposit_by_credit_cards(self):
        with transaction.atomic():
            if not self.ban_deposit_with_credit_bank_cards:
                Notification.send(
                    recipient=self,
                    title='غیر فعال شدن واریز با کارت‌های هدیه و مجازی',
                    message='در راستای افزایش امنیت حساب کاربری شما، واریز با کارت‌های هدیه و مجازی غیر فعال شد. توجه داشته باشید که همچنان می‌توانید با کارت‌های اعتباری از طریق درگاه پرداخت، حساب خود را شارژ نمایید.'
                )

            self.ban_deposit_with_credit_bank_cards = True
            self.save(update_fields=['ban_deposit_with_credit_bank_cards'])

            from financial.models import BankCard

            cards = BankCard.objects.filter(user=self, verified=True, deleted=False)

            for card in cards.filter(type__in=BankCard.CREDIT_FAMILY_TYPES):
                card.reject(BankCard.CREDIT_CARD)

            for card in cards.filter(type=''):
                card.verified = None
                card.save(update_fields=['verified'])


@receiver(post_save, sender=User)
def handle_user_save(sender, instance: User, created, **kwargs):
    if settings.DEBUG_OR_TESTING_OR_STAGING:
        return

    producer = get_kafka_producer()
    account = instance.get_account()

    if account.type != Account.ORDINARY:
        return

    referrer_id = None

    referrer = account.referred_by and account.referred_by.owner.user

    if referrer:
        referrer_id = referrer.id

    if not instance.mission_journey:
        promotion = ''
    else:
        promotion = instance.mission_journey.name

    event = UserEvent(
        user_id=instance.id,
        first_name=instance.first_name,
        last_name=instance.last_name,
        referrer_id=referrer_id,
        created=instance.date_joined,
        event_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, str(instance.id) + UserEvent.type)),
        level_2_verify_datetime=instance.level_2_verify_datetime,
        level_3_verify_datetime=instance.level_3_verify_datetime,
        level=instance.level,
        birth_date=instance.birth_date,
        can_withdraw=instance.can_withdraw,
        can_trade=instance.can_trade,
        promotion=promotion,
        chat_uuid=instance.chat_uuid,
        verify_status=instance.verify_status,
        reject_reason=instance.reject_reason,
        first_fiat_deposit_date=instance.first_fiat_deposit_date,
        first_crypto_deposit_date=instance.first_crypto_deposit_date,
    )
    producer.produce(event)


class LevelGrants(models.Model):
    LEVEL1 = 1
    LEVEL2 = 2
    LEVEL3 = 3
    LEVEL4 = 4

    level = models.PositiveSmallIntegerField(
        unique=True,
        default=LEVEL1,
        choices=(
            (LEVEL1, 'level 1'), (LEVEL2, 'level 2'), (LEVEL3, 'level 3'),
            (LEVEL4, 'level 4'),
        ),
        verbose_name='سطح',
    )

    max_daily_crypto_withdraw = models.PositiveBigIntegerField(null=True, blank=True, default=0)
    max_daily_fiat_withdraw = models.PositiveBigIntegerField(null=True, blank=True, default=0)

    max_daily_fiat_deposit = models.PositiveBigIntegerField(null=True, blank=True, default=None)

    class Meta:
        verbose_name_plural = "Level Grants"

    @classmethod
    def get_level_grants(cls, level: int) -> 'LevelGrants':
        return LevelGrants.objects.filter(level=level).last() or LevelGrants()

    @classmethod
    def get_max_daily_crypto_withdraw(cls, user: 'User'):
        return user.custom_crypto_withdraw_ceil or LevelGrants.get_level_grants(user.level).max_daily_crypto_withdraw

    @classmethod
    def get_max_daily_fiat_withdraw(cls, user: 'User'):
        return user.custom_fiat_withdraw_ceil or LevelGrants.get_level_grants(user.level).max_daily_fiat_withdraw
