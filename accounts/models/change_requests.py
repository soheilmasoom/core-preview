import logging
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import User, EmailNotification, Notification, LoginActivity
from accounts.models.sms_notification import SmsNotification
from accounts.utils.validation import PHONE_MAX_LENGTH, get_jalali_now
from accounts.validators import mobile_number_validator
from ledger.utils.fields import PENDING, get_status_field, CANCELED, DONE

logger = logging.getLogger(__name__)


class BaseChangeRequest(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    status = get_status_field()

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    selfie_image = models.OneToOneField(
        to='multimedia.Image',
        on_delete=models.PROTECT,
        verbose_name='عکس سلفی',
        related_name='+',
        blank=True,
        null=True
    )

    def accept(self):
        pass

    def reject(self):
        pass

    class Meta:
        abstract = True


class Forget2FA(BaseChangeRequest):

    def accept(self):
        assert self.status == PENDING

        user = self.user
        context = {
            'brand': settings.BRAND
        }

        content = render_to_string('accounts/notif/sms/2fa_forget_success', context=context)

        with transaction.atomic():
            SmsNotification.objects.create(
                recipient=user,
                content=content
            )

            self.status = DONE
            self.save(update_fields=['status'])

            TOTPDevice.objects.filter(user=user).update(confirmed=False)
            user.suspend(duration=timedelta(days=1))

    def reject(self):
        assert self.status == PENDING

        user = self.user
        context = {'brand': settings.BRAND}
        content = render_to_string('accounts/notif/sms/2fa_forget_reject', context=context)

        with transaction.atomic():
            SmsNotification.objects.create(
                recipient=user,
                content=content
            )

            self.status = CANCELED
            self.save(update_fields=['status'])

    class Meta:
        verbose_name = 'درخواست فراموشی شناسه دوعاملی'
        verbose_name_plural = 'درخواست‌های فراموشی شناسه دوعاملی'


class ChangePhone(BaseChangeRequest):
    new_phone = models.CharField(
        max_length=PHONE_MAX_LENGTH,
        validators=[mobile_number_validator],
        verbose_name='شماره موبایل جدید',
        db_index=True,
        null=True,
        blank=True,
    )

    def archiveRegisteredPhone(self):
        user = self.user
        archived_phone = "00" + user.phone

        account = user.get_account()
        errors = []
        if user.level == User.LEVEL1:
            if user.has_zero_balance(account):
                user.phone = archived_phone
                user.username = archived_phone
                user.save(update_fields=['phone', 'username'])
            else:
                errors.append("موجودی کاربر صفر نیست")
        else:
            errors.append("کاربر سطح یک نیست")
        if errors:
            raise ValidationError(errors)


    def accept(self):
        with transaction.atomic():
            user = self.user
            new_phone = self.new_phone

            user.phone = new_phone
            user.username = new_phone

            user.suspend(timedelta(days=1), 'تغییر شماره‌ موبایل')
            user.save(update_fields=['phone', 'username'])

            EmailNotification.send_by_template(
                recipient=user,
                template='change_phone_successful',
                check_spam=True,
                context={
                    'now': get_jalali_now(),
                }
            )

            Notification.send(
                recipient=user,
                title='تغییر شماره موبایل',
                message='شماره موبایل شما با موفقیت تغییر یافت.',
                link='/account'
            )

            self.status = DONE
            self.save(update_fields=['status'])

            logins = LoginActivity.objects.filter(
                Q(session__isnull=False, session__expire_date__gt=timezone.now()) |
                Q(refresh_token__isnull=False),
                user=self.user
            )

            for login in logins:
                login.destroy()

    def reject(self):
        with transaction.atomic():
            EmailNotification.send_by_template(
                recipient=self.user,
                template='change_phone_rejection',
                check_spam=True,
                context={
                    'now': get_jalali_now(),
                }
            )

            Notification.send(
                recipient=self.user,
                title='تغییر شماره موبایل',
                message='درخواست تغییر شماره موبایل شما پذیرفته نشد.',
                link='/account'
            )

            self.status = CANCELED
            self.save(update_fields=['status'])

    class Meta:
        verbose_name = 'درخواست تغییر شماره موبایل'
        verbose_name_plural = 'درخواست‌های تغییر شماره موبایل'
