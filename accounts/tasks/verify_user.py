import logging
from pipes import Template

from celery import shared_task
from decouple import config
from django.conf import settings

from accounts.models import Notification, TemplateType
from accounts.models import User
from accounts.verifiers.basic_verifier import verify_national_code_with_phone, basic_verify
from .send_sms import send_message_by_kavenegar

logger = logging.getLogger(__name__)


@shared_task(queue='kyc')
def basic_verify_user(user_id: int):
    user = User.objects.get(id=user_id)  # type: User
    basic_verify(user)


@shared_task(queue='kyc')
def verify_user_national_code(user_id: int):
    user = User.objects.get(id=user_id)  # type: User
    verify_national_code_with_phone(user)


def alert_user_verify_status(user: User):
    if user.verify_status == User.PENDING:
        return
    title = 'احراز هویت'
    notif_message = ''

    if user.level >= User.LEVEL2 or user.verify_status == User.REJECTED:
        if user.verify_status == User.REJECTED:
            if user.reject_reason == User.NATIONAL_CODE_DUPLICATED:
                notif_message = 'شما قبلا در {} با شماره موبایل دیگری ثبت‌نام کرده‌اید و احراز هویت‌تان انجام شده ' \
                                'است. لطفا از آن حساب استفاده کنید.'.format(
                    settings.BRAND)
            else:
                notif_message = 'اطلاعات وارد شده نیاز به بازنگری دارد.'
            level = Notification.ERROR
            template = TemplateType.LEVELUP_REJECTED
            levelup = ''
        else:
            if user.level == User.LEVEL2:
                if settings.EXCHANGE_TYPE.is_crypto:
                    notif_message = 'احراز هویت شما با موفقیت انجام شد. هم اکنون می‌توانید خرید و فروش تمامی رمزارز‌ها را انجام دهید.'
                else:
                    notif_message = f'احراز هویت شما با موفقیت انجام شد. هم اکنون می‌توانید خرید و فروش در {settings.BRAND} را آغاز کنید.'
            else:
                notif_message = 'احراز هویت سطح {} شما با موفقیت انجام شد.'.format(user.level)
            level = Notification.SUCCESS
            template = TemplateType.LEVELUP_ACCEPTED
            levelup = ''
        Notification.send(
            recipient=user,
            title=title,
            level=level,
            message=notif_message
        )
        send_message_by_kavenegar(
            phone=user.phone,
            template=template,
            token=str(levelup)
        )
