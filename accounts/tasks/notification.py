import logging
import time
from datetime import timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from accounts.models import Notification, BulkNotification, User, EmailNotification
from accounts.models.sms_notification import SmsNotification
from accounts.tasks.send_sms import send_kavenegar_exclusive_sms
from accounts.utils.email import send_email, EmailInfo
from accounts.utils.fcm_topic import fcm_topic_manager
from accounts.utils.push_notif import send_push_notif_to_user, trigger_topic_subscriptions
from ledger.utils.fields import PENDING, DONE

logger = logging.getLogger(__name__)


@shared_task(queue='notif-manager')
def send_notifications_push():
    Notification.objects.filter(
        push_status=Notification.PUSH_WAITING,
        created__lt=timezone.now() - timedelta(hours=1)
    ).update(
        push_status=Notification.PUSH_CANCELED
    )

    for notif in Notification.objects.filter(push_status=Notification.PUSH_WAITING).order_by('id')[:100]:
        send_push_notif_to_user(
            user=notif.recipient,
            title=notif.title,
            body=notif.message,
            image=notif.image,
            link=notif.link
        )

        notif.push_status = Notification.PUSH_SENT
        notif.save(update_fields=['push_status'])


@shared_task(queue='notif-manager')
def send_telegram_bot_notifications():
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    notifs_to_send = []
    for notif in Notification.objects.filter(sent_telegram=False).order_by('id')[:100]:
        if notif.recipient.send_notifs_to_telegram_bot:
            notifs_to_send.append(notif)
            notif.sent_telegram = True
            notif.save(update_fields=['sent_telegram'])
            print("added")

    notification_json = {
        "notifications": [
            {
                "notification_id": notif.id,
                "recipient_id": notif.recipient.id,
                "title": notif.title,
                "message": notif.message,
                "link": notif.link,
                "level": notif.level,
                "image": notif.image,
            }
            for notif in notifs_to_send
        ]
    }
    headers = {
        "Authorization": f"Token {settings.TELEGRAM_BOT_TOKEN}"
    }
    response = requests.post("http://127.0.0.1:8000/bot/notif/", json=notification_json, headers=headers)

    logger.info(f"Sending single push notif to telegram {'succeeded' if response.ok else 'failed'}")


@shared_task(queue='notif-manager')
def process_bulk_notifications():
    for bulk_notif in BulkNotification.objects.filter(status=PENDING):
        sent_users = list(Notification.objects.filter(group_id=bulk_notif.group_id).values_list('recipient', flat=True))

        notifs = []

        for u in User.objects.exclude(id__in=sent_users):
            notifs.append(
                Notification(
                    recipient=u,
                    group_id=bulk_notif.group_id,
                    title=bulk_notif.title,
                    message=bulk_notif.message,
                    link=bulk_notif.link,
                    level=bulk_notif.level,
                    push_status=Notification.PUSH_WAITING
                )
            )

            if len(notifs) > 1000:
                Notification.objects.bulk_create(notifs)
                notifs = []

        if notifs:
            Notification.objects.bulk_create(notifs)

        bulk_notif.status = DONE
        bulk_notif.save(update_fields=['status'])


@shared_task(queue='notif-manager')
def send_sms_notifications():
    for notif in SmsNotification.objects.filter(sent=False).order_by('id')[:1000]:
        resp = send_kavenegar_exclusive_sms(
            phone=notif.recipient.phone,
            content=notif.content
        )

        if resp:
            notif.sent = True
            notif.save(update_fields=['sent'])


@shared_task(queue='notif-manager')
def send_email_notifications():
    for email_notif in EmailNotification.objects.filter(sent=False).order_by('id'):
        if not email_notif.recipient.email:
            email_notif.sent = True
            email_notif.save(update_fields=['sent'])
            logger.info(f'SendingMailIgnoredDueToNullEmail user:{email_notif.recipient.id}')
            continue

        email_info = EmailInfo(
            title=email_notif.title,
            body_html=email_notif.content_html,
            body=email_notif.content
        )

        if send_email(email_notif.recipient.email, email_info):
            email_notif.sent = True
            email_notif.save(update_fields=['sent'])


@shared_task(queue='notif-manager')
def trigger_fcm_topic_subscriptions(iterations: int = 1000):
    for i in range(iterations):
        pending_tokens = fcm_topic_manager.get_pending_tokens()

        if not pending_tokens:
            return

        trigger_topic_subscriptions(pending_tokens)
        time.sleep(0.1)
