
import logging
import time
from datetime import timedelta
from typing import List

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from accounts.models import Notification, BulkNotification, User, EmailNotification, FirebaseToken
from accounts.models.sms_notification import SmsNotification
from accounts.tasks.send_sms import send_kavenegar_exclusive_sms
from accounts.utils.email import send_email, EmailInfo
from accounts.utils.fcm_topic import fcm_topic_manager
from accounts.utils.push_notif import send_push_notif_to_user, trigger_topic_subscriptions
from accounts.utils.firebase_service import firebase_service, PushNotificationPayload
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
    
    pending_notifs = list(
        Notification.objects
        .filter(push_status=Notification.PUSH_WAITING)
        .select_related('recipient')
        .order_by('id')[:100]
    )
    
    if not pending_notifs:
        return
    
    user_notifs = {}
    for notif in pending_notifs:
        user_id = notif.recipient_id
        if user_id not in user_notifs:
            user_notifs[user_id] = []
        user_notifs[user_id].append(notif)
    
    for user_id, notifs in user_notifs.items():
        user = notifs[0].recipient
        
        tokens = list(
            FirebaseToken.live_objects
            .filter(user=user)
            .values_list('token', flat=True)
        )
        
        if not tokens:
            for notif in notifs:
                notif.push_status = Notification.PUSH_CANCELED
                notif.save(update_fields=['push_status'])
            continue
        
        for notif in notifs:
            payload = PushNotificationPayload(
                title=notif.title,
                body=notif.message,
                image=notif.image,
                link=notif.link,
                data={
                    'notification_id': str(notif.id),
                    'level': notif.level,
                }
            )
            
            if len(tokens) == 1:
                result = firebase_service.send_to_token(tokens[0], payload)
                success = result is not None
            else:
                result = firebase_service.send_multicast(tokens, payload)
                success = result['success_count'] > 0
            
            notif.push_status = Notification.PUSH_SENT if success else Notification.PUSH_CANCELED
            notif.save(update_fields=['push_status'])


@shared_task(queue='notif-manager')
def send_telegram_bot_notifications():
    if not settings.KAFTAR_TOKEN:
        return

    notifs_to_send = list(Notification.objects.filter(
        sent_telegram=False,
    ).order_by('id')[:1000])

    data = {
        "notifs": [
            {
                "id": notif.id,
                "user_id": notif.recipient_id,
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
        "Authorization": f"Token {settings.KAFTAR_TOKEN}"
    }
    url = settings.KAFTAR_HOST_URL + '/api/v1/bot/notif/'

    resp = requests.post(url, json=data, headers=headers)

    if resp.ok:
        Notification.objects.filter(id__in=[notif.id for notif in notifs_to_send]).update(sent_telegram=True)


@shared_task(queue='notif-manager')
def process_bulk_notifications():
    for bulk_notif in BulkNotification.objects.filter(status=PENDING):
        sent_users = list(
            Notification.objects
            .filter(group_id=bulk_notif.group_id)
            .values_list('recipient', flat=True)
        )

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


@shared_task(queue='notif-manager')
def cleanup_inactive_tokens():
    deleted_count = FirebaseToken.objects.filter(
        active=False,
        created__lt=timezone.now() - timedelta(days=30)
    ).delete()[0]
    
    logger.info(f"Cleaned up {deleted_count} old inactive tokens")
    return deleted_count
