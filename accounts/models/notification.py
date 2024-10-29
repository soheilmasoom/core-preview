import logging

from django.db import models
from django.db.models import UniqueConstraint, Q, Sum
from django.utils import timezone

from ledger.utils.fields import get_group_id_field, get_status_field

logger = logging.getLogger(__name__)


NOTIFICATION_TEMPLATES = {
    'plain': '{last}',
    'like': '{last} و {count} نفر دیگر پست شما را پسندیدند',
    'comment': '{last} و {count} نفر دیگر برای پست شما نظر گذاشتند',
    'follow': '{last} و {count} نفر دیگر شما را دنبال کردند'
}

NOTIFICATION_0_TEMPLATES = {
    'plain': '{last}',
    'like': '{last} پست شما را پسندید',
    'comment': '{last} برای پست شما نظر گذاشت',
    'follow': '{last} شما را دنبال کرد'
}


class LiveNotification(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(read=False)


class Notification(models.Model):
    INFO, SUCCESS, WARNING, ERROR = 'info', 'success', 'warning', 'error'
    LEVEL_CHOICES = ((INFO, INFO), (SUCCESS, SUCCESS), (WARNING, WARNING), (ERROR, ERROR))

    PUSH_WAITING, PUSH_SENT, PUSH_CANCELED = 'w', 's', 'c'

    CORE, NINJA, CRM = 'core', 'ninja', 'crm'
    SOURCES = ((CORE, CORE), (NINJA, NINJA), (CRM, CRM))

    LIKE, COMMENT, FOLLOW, PLAIN = 'like', 'comment', 'follow', 'plain'
    TEMPLATE_CHOICES = ((LIKE, LIKE), (COMMENT, COMMENT), (FOLLOW, FOLLOW), (PLAIN, PLAIN))
    TEMPLATE_LIST = [LIKE, COMMENT, FOLLOW, PLAIN]

    ORDINARY, REPLACEABLE, DIFF = 'ord', 'rep', 'dif'
    TYPE_CHOICE = ((ORDINARY, ORDINARY), (REPLACEABLE, REPLACEABLE), (DIFF, DIFF))

    created = models.DateTimeField(default=timezone.now)
    read_date = models.DateTimeField(null=True, blank=True)

    recipient = models.ForeignKey(to='accounts.User', on_delete=models.CASCADE)

    title = models.CharField(max_length=128)
    link = models.CharField(blank=True, max_length=128)
    message = models.CharField(max_length=512, blank=True)

    image = models.URLField(blank=True)

    level = models.CharField(
        max_length=8,
        choices=LEVEL_CHOICES,
        default=INFO
    )

    read = models.BooleanField(default=False)
    hidden = models.BooleanField(default=False)

    push_status = models.CharField(
        choices=((PUSH_WAITING, 'waiting'), (PUSH_SENT, 'sent'), (PUSH_CANCELED, 'canceled')),
        blank=True,
        max_length=1,
        db_index=True
    )

    group_id = get_group_id_field(null=True, db_index=True, default=None)

    source = models.CharField(
        max_length=8,
        choices=SOURCES,
        default=CORE
    )
    type = models.CharField(
        max_length=3,
        choices=TYPE_CHOICE,
        default=ORDINARY
    )
    template = models.CharField(
        max_length=8,
        choices=TEMPLATE_CHOICES,
        default=PLAIN
    )
    count = models.IntegerField(default=0, null=True, blank=True)

    objects = models.Manager()
    live_objects = LiveNotification()

    class Meta:
        ordering = ('-created', )
        indexes = [
            models.Index(fields=['recipient', 'read', 'hidden'], name="notification_idx")
        ]

        constraints = [
            UniqueConstraint(
                name='unique_unread_group_id',
                fields=["group_id", "template"],
                condition=Q(read=False) & Q(source='ninja')
            ),
            UniqueConstraint(
                name='unique_recipient_group_id',
                fields=['recipient', 'group_id'],
                condition=Q(template='plain')
            )
        ]

    @classmethod
    def send(cls, recipient, title: str, link: str = '', message: str = '', level: str = INFO, image: str = '',
             send_push: bool = True, group_id=None, type: str = ORDINARY, template: str = PLAIN, source: str = CORE,
             count: int = 1):
        count -= 1

        if not recipient:
            logger.info('failed to send notif')
            return
        if not template in Notification.TEMPLATE_LIST:
            raise NotImplementedError

        if type == cls.DIFF:
            read_count = Notification.objects.filter(group_id=group_id, read=True).aggregate(Sum('count'))[
                'count__sum']
            if read_count:
                count = count - read_count
            if count <= 0:
                message = NOTIFICATION_0_TEMPLATES.get(template, '').format(last=message)
            else:
                message = NOTIFICATION_TEMPLATES.get(template, '').format(last=message, count=count)

        if type == cls.ORDINARY:
            if Notification.live_objects.filter(group_id=group_id, source=cls.NINJA).exists():
                return

            notification = Notification.objects.create(
                recipient=recipient,
                template=template,
                title=title,
                link=link,
                message=message,
                level=level,
                source=source,
                image=image,
                type=type,
                count=count,
                push_status=Notification.PUSH_WAITING if send_push else '',
                group_id=group_id

            )
        elif not group_id:
            logger.info('failed to send notif, uuid error')
            return

        elif type in [cls.REPLACEABLE, cls.DIFF]:
            notification, _ = Notification.objects.update_or_create(
                group_id=group_id,
                template=template,
                read=False,
                defaults={
                    'title': title,
                    'link': link,
                    'message': message,
                    'image': image,
                    'count': count,
                    'source': source,
                    'type': type,
                    'level': level,
                    'recipient': recipient,
                    'push_status': Notification.PUSH_WAITING if send_push else '',
                }
            )
        else:
            logger.info('failed to send notif')
            return

        return notification

    def make_read(self):
        if not self.read:
            self.read = True
            self.read_date = timezone.now()
            self.save()


class BulkNotification(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    group_id = get_group_id_field()
    status = get_status_field()

    title = models.CharField(max_length=128)
    link = models.CharField(blank=True, max_length=128)
    message = models.TextField(blank=True)

    level = models.CharField(
        max_length=8,
        choices=Notification.LEVEL_CHOICES,
        default=Notification.INFO
    )
