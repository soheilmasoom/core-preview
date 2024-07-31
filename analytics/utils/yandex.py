import json
import logging
from datetime import datetime

import requests
from decouple import config

from accounts.models import User, TrafficSource

logger = logging.getLogger(__name__)


def send_yandex_event(user: User, name: str, data: dict = None):
    yandex_api_key = config('YANDEX_API_KEY', None)
    yandex_application_id = config('YANDEX_APPLICATION_ID', None)

    if not yandex_api_key or not yandex_application_id:
        logger.info(f'Sending yandex event ({name}) for {user} ignored due to config')
        return

    source = getattr(user, 'traffic_source')  # type: TrafficSource

    profile_id = source and source.yandex_profile_id

    if not profile_id:
        logger.info(f'Sending yandex event ({name}) for {user} ignored due to profile_id')
        return

    data = data or {}

    request_data = {
        'post_api_key': yandex_api_key,
        'application_id': yandex_application_id,
        'event_timestamp': int(datetime.utcnow().timestamp()),
        'profile_id': profile_id,
        'event_name': name,
    }

    if data:
        request_data['event_json'] = json.dumps(data)

    try:
        resp = requests.post(
            url='https://api.appmetrica.yandex.ru/logs/v1/import/events',
            params=request_data,
            timeout=15
        )

        if not resp.ok:
            logger.info(f'Sending yandex event ({name}) for {user} failed {resp.json()}')

        return resp.ok

    except Exception as exp:
        logger.exception(f'Sending yandex event ({name}) for {user} failed {exp}')
        return False
