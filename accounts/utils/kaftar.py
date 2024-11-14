import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_message(profile: str, text: str):
    token = settings.KAFTAR_TOKEN

    if settings.DEBUG_OR_TESTING:
        print('send to %s' % profile)
        print(text)

    if not profile or not token:
        logger.info('No kaftar token set!')
        return

    try:
        requests.post(
            f'{settings.KAFTAR_HOST_URL}/api/v1/messaging/send/',
            headers={
                'Authorization': token
            },
            data={
                'profile': profile,
                'text': text
            },
            timeout=5,
        )
    except:
        pass
