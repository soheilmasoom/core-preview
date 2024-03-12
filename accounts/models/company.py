import json

from django.db import models, transaction

from accounts.utils.similarity import clean_persian_name
from accounts.validators import company_national_id_validator
from accounts.models import User
from accounts.verifiers.utils import ServerError
from ledger.utils.fields import get_verify_status_field, REJECTED, VERIFIED

import logging

logger = logging.getLogger(__name__)


class Company(models.Model):
    name = models.CharField(blank=True, max_length=128)
    address = models.TextField(blank=True)
    postal_code = models.CharField(blank=True, max_length=128)
    registration_id = models.CharField(blank=True, max_length=128)
    company_registration_date = models.CharField(blank=True, max_length=128)
    national_id = models.CharField(validators=[company_national_id_validator], unique=True, max_length=11)
    is_active = models.BooleanField(null=True, blank=True)
    company_documents = models.OneToOneField(
        to='multimedia.File',
        on_delete=models.PROTECT,
        verbose_name='مدارک شرکت',
        related_name='+',
        blank=True,
        null=True
    )

    user = models.OneToOneField(User, on_delete=models.PROTECT)

    provider_data = models.JSONField(null=True, blank=True)
    status = get_verify_status_field()

    def verify_and_fetch_company_data(self, retry: int = 2):
        from accounts.verifiers.zibal import ZibalRequester
        requester = ZibalRequester(user=self.user)
        try:
            data = requester.company_information(self.national_id).data
            if data.code == "SUCCESSFUL":
                self.name = clean_persian_name(data.title)
                self.address = clean_persian_name(data.address)
                self.postal_code = data.postal_code
                self.registration_id = data.registration_id
                self.is_active = clean_persian_name(data.status) == 'فعال'
                self.company_registration_date = data.establishment_date
                self.provider_data = json.dumps(data, default=lambda o: o.__dict__)
                self.save(
                    update_fields=[
                        'name', 'address', 'postal_code', 'registration_id', 'provider_data', 'is_active',
                        'company_registration_date'
                    ]
                )
        except (TimeoutError, ServerError):
            if retry == 0:
                logger.error('company information retrieval timeout')
                return
            else:
                logger.info('Retrying company information fetching..')
                return self.verify_and_fetch_company_data(retry - 1)

    def accept(self):
        from accounts.models import EmailNotification, Notification

        with transaction.atomic():
            self.status = VERIFIED
            self.user.level = 4
            self.save(update_fields=['status'])
            self.user.save(update_fields=['level'])
            EmailNotification.objects.create(
                recipient=self.user,
                title='تایید درخواست',
                content='درخواست ثبت نام حساب حقوقی با موفقیت تایید شد.',
                content_html='درخواست ثبت نام حساب حقوقی با موفقیت تایید شد.'
            )
            Notification.objects.create(
                recipient=self.user,
                title='تایید درخواست',
                message='درخواست ثبت نام حساب حقوقی با موفقیت تایید شد.'
            )

    def reject(self):
        from accounts.models import EmailNotification, Notification

        with transaction.atomic():
            self.status = REJECTED
            self.save(update_fields=['status'])
            EmailNotification.objects.create(
                recipient=self.user,
                title='رد درخواست',
                content='درخواست ثبت نام حساب حقوقی رد شد. لطفا برای دریافت اطلاعات بیشتر با پشتیبان تماس بگیرید.',
                content_html='درخواست ثبت نام حساب حقوقی رد شد. لطفا برای دریافت اطلاعات بیشتر با پشتیبان تماس بگیرید.'
            )
            Notification.objects.create(
                recipient=self.user,
                title='رد درخواست',
                message='درخواست ثبت نام حساب حقوقی رد شد. لطفا برای دریافت اطلاعات بیشتر با پشتیبان تماس بگیرید.'
            )

    class Meta:
        verbose_name = 'شرکت'
        verbose_name_plural = 'شرکت‌ها'
