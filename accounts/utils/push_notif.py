import dataclasses
import json
import logging
import time

import requests
from decouple import config
from oauth2client.service_account import ServiceAccountCredentials

from accounts.models import User

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AccessToken:
    time: float
    project_id: str
    token: str


_access_token = AccessToken(time=0, project_id="", token="")


def _get_access_token() -> AccessToken:
    global _access_token

    now = time.time()

    if now - _access_token.time >= 3600:
        scopes = ['https://www.googleapis.com/auth/firebase.messaging']
        logger.warning(f"firebase_dict {config('FIREBASE_SECRET_JSON')}")
        firebase_dict = json.loads(config('FIREBASE_SECRET_JSON', ''))

        credentials = ServiceAccountCredentials._from_parsed_json_keyfile(firebase_dict, scopes)
        access_token_info = credentials.get_access_token()

        _access_token = AccessToken(
            time=now,
            project_id=firebase_dict['project_id'],
            token=access_token_info.access_token,
        )

    return _access_token

def manage_user_topic_subscription(user: User, topic: str, action: str) -> bool:
    from accounts.models import FirebaseToken

    tokens = FirebaseToken.objects.filter(user=user).values_list('token', flat=True)
    if not tokens:
        logger.info(f'No tokens found for user ID: {user}')
        return False

    access_token = _get_access_token()
    url = 'https://iid.googleapis.com/iid/v1:batchAdd' if action == 'subscribe' else 'https://iid.googleapis.com/iid/v1:batchRemove'

    resp = requests.post(
        url=url,
        headers={
            'Authorization': f'Bearer {access_token.token}',
            'Content-Type': 'application/json',
            'access_token_auth': 'true'
        },
        json={
            'to': f'/topics/{topic}',
            'registration_tokens': list(tokens)
        }
    )
    url=url,
    headers_resp={
        'Authorization': f'Bearer {access_token.token}',
        'Content-Type': 'application/json',
    },
    json_resp={
        'to': f'/topics/{topic}',
        'registration_tokens': list(tokens)
    }
    logger.warning(f'json {json_resp} --- {headers_resp} {action} user ID {user} to topic: {topic}')
    if resp.ok:
        logger.warning(f'{action} user ID {user} to topic: {topic}')
    else:
        logger.warning(f'Failed to {action} user ID {user} to topic: {topic} Response: {resp.text}-{resp}')
    return resp.ok


def send_push_notif_to_user(user: User, title: str, body: str, image: str = None, link: str = None):
    from accounts.models import FirebaseToken

    for firebase_token in FirebaseToken.objects.filter(user=user):
        send_push_notif(title, body, firebase_token.token, image, link)


def send_push_notif(title: str, body: str, token: str = None, image: str = None, link: str = None, topic: str = None):
    notification = {
        "body": body,
        "title": title
    }

    if image:
        notification['image'] = image

    body = {
        "notification": notification
    }

    if token:
        body['token'] = token

    if topic:
        body['topic'] = topic

    if link:
        body['webpush'] = {
            'fcm_options': {
                'link': link
            }
        }

    access_token = _get_access_token()

    resp = requests.post(
        url=f'https://fcm.googleapis.com/v1/projects/{access_token.project_id}/messages:send',
        headers={
            'Authorization': 'Bearer ' + access_token.token,
            'Content-Type': 'application/json; UTF-8',
        },
        json={
            'message': body
        },
        timeout=30,
    )

    if not resp.ok:
        logger.info(body)
        logger.info(resp.status_code)
        logger.info(resp.json())

    if resp.status_code == 404:
        from accounts.models import FirebaseToken
        data = resp.json()

        if data['error']['status'] == 'NOT_FOUND':
            FirebaseToken.objects.filter(token=token).delete()

    return resp.ok
