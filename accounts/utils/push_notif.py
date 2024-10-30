import dataclasses
import json
import logging
import time

import requests
from decouple import config
from oauth2client.service_account import ServiceAccountCredentials

from accounts.models import User, FirebaseToken
from accounts.utils.fcm_topic import PendingTokens, fcm_topic_manager

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
        firebase_dict = json.loads(config('FIREBASE_SECRET_JSON', ''))

        credentials = ServiceAccountCredentials._from_parsed_json_keyfile(firebase_dict, scopes)
        access_token_info = credentials.get_access_token()

        _access_token = AccessToken(
            time=now,
            project_id=firebase_dict['project_id'],
            token=access_token_info.access_token,
        )

    return _access_token


def trigger_topic_subscriptions(pending_tokens: PendingTokens):
    access_token = _get_access_token()

    if pending_tokens.action == pending_tokens.SUBSCRIBE:
        url = 'https://iid.googleapis.com/iid/v1:batchAdd'
    else:
        url = 'https://iid.googleapis.com/iid/v1:batchRemove'

    tokens = pending_tokens.tokens

    resp = requests.post(
        url=url,
        headers={
            'Authorization': f'Bearer {access_token.token}',
            'Content-Type': 'application/json',
            "access_token_auth": "true",
        },
        json={
            'to': f'/topics/{pending_tokens.topic}',
            'registration_tokens': pending_tokens.tokens,
        },
    )

    resp_json = resp.json()

    if not resp.ok:
        logger.info(f"Unable to trigger subscription for {pending_tokens.action}/{pending_tokens.topic}")
        return False

    to_delete_tokens = []
    invalid_tokens = []

    for idx, result in enumerate(resp_json['results']):
        token = tokens[idx]

        if 'error' in result:
            error = result['error']

            logger.info(f'Error subscribing token {token} to {pending_tokens.topic} {error}')

            if error in ['NOT_FOUND', 'INVALID_ARGUMENT', 'PERMISSION_DENIED']:
                invalid_tokens.append(token)
                FirebaseToken.objects.filter(token=token).update(active=False, error=error)

        else:
            to_delete_tokens.append(token)

    if to_delete_tokens:
        pending_tokens.tokens = to_delete_tokens
        fcm_topic_manager.remove_pending_tokens(pending_tokens)

    fcm_topic_manager.cleanup_tokens(invalid_tokens)

    return True


def send_push_notif_to_user(user: User, title: str, body: str, image: str = None, link: str = None):
    from accounts.models import FirebaseToken

    for firebase_token in FirebaseToken.live_objects.filter(user=user):
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

    if resp.status_code == 404:
        from accounts.models import FirebaseToken
        data = resp.json()
        error = data['error']['status']
        if error in ['NOT_FOUND', 'INVALID_ARGUMENT', 'PERMISSION_DENIED']:
            FirebaseToken.live_objects.filter(token=token).update(active=False, error=error)

    return resp.ok
