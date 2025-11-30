import logging
from dataclasses import dataclass

import requests
from decouple import config
from django.conf import settings
from django.template import loader
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@dataclass
class EmailInfo:
    title: str
    body: str
    body_html: str


def send_email(email: str, info: EmailInfo):
    return _send_email(
        subject=info.title,
        body_html=render_to_string("accounts/notif/base/email_template.min.html", {
            'title': info.title,
            'body_html': info.body_html,
            'brand': settings.BRAND,
            'panel_url': settings.PANEL_URL,
            'logo_elastic_url': config('LOGO_ELASTIC_URL', ''),
        }),
        body_text=info.body,
        to=[email]
    )


def _send_email(subject: str, body_html: str, body_text: str, to: list, transactional: bool = True,
               purpose: str = 'Notification'):

    if settings.DEBUG_OR_TESTING_OR_STAGING:
        return print(subject, body_html, body_text, purpose, to)

    resp = requests.post(
        'https://api.elasticemail.com/v2/email/send',
        params={
            'apikey': config('ELASTICMAIL_API_KEY'),
            'subject': subject,
            'bodyHtml': body_html,
            'bodyText': body_text,
            'charset': 'utf-8',
            'from': config('EMAIL_SENDER'),
            'fromName': settings.BRAND,
            'isTransactional': transactional,
            'msgTo': ','.join(to),
            'utmSource': 'ElasticEmail',
            'utmMedium': 'Email',
            'utmContent': settings.BRAND_EN,
            'utmCampaign': purpose,
        },
        timeout=30,
    )

    data = resp.json()

    if not resp.ok or not data['success']:
        logger.error("Error sending email to elastic", extra={
            'subject': subject,
            'status': resp.status_code,
            'data': data
        })

        logger.info('elasticmail error', data)
        return

    return data


def load_email_template(template: str, context: dict = None) -> EmailInfo:
    body_html = loader.render_to_string(
        f'accounts/notif/email/{template}/body.html',
        context=context)

    body = loader.render_to_string(
        f'accounts/notif/email/{template}/body.txt',
        context=context)

    title = loader.render_to_string(f'accounts/notif/email/{template}/title.txt') + ' | ' + settings.BRAND

    return EmailInfo(
        title=title,
        body=body,
        body_html=body_html,
    )
