from django.db import models
from django.utils import timezone

from accounts.models import User
from accounts.utils.email import load_email_template
from ledger.utils.fields import get_group_id_field


class EmailNotification(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    recipient = models.ForeignKey(to='accounts.User', on_delete=models.CASCADE)
    title = models.CharField(max_length=250)
    content = models.TextField()
    content_html = models.TextField()
    sent = models.BooleanField(default=False, db_index=True)

    group_id = get_group_id_field(null=True, db_index=True, default=None)

    @staticmethod
    def is_spam(recipient, title: str) -> bool:
        return EmailNotification.objects.filter(
            recipient=recipient,
            title=title,
            created__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).exists()

    class Meta:
        ordering = ('-created',)
        unique_together = ('recipient', 'group_id')
        indexes = [
            models.Index(fields=['recipient', 'title', 'created'], name="email_notification_idx"),
        ]

    @classmethod
    def send_by_template(cls, recipient: User, template: str, context: dict = None, check_spam: bool = False):
        if not recipient.email:
            return

        email_info = load_email_template(template, context)

        if check_spam and cls.is_spam(recipient, email_info.title):
            return

        EmailNotification.objects.create(
            recipient=recipient,
            title=email_info.title,
            content=email_info.body,
            content_html=email_info.body_html
        )
