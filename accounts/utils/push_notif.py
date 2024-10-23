import dataclasses
import json
import logging
import time

import requests
from decouple import config
from oauth2client.service_account import ServiceAccountCredentials

from accounts.models import User
from accounts.models.fcm_topic_subscription import FCMTopicSubscription
from ledger.utils.fields import DONE

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

def manage_user_topic_subscription(fcm_topic_subscription: FCMTopicSubscription, user: User, topic: str, action: str, token: str = None):
    from accounts.models import FirebaseToken

    tokens = list(FirebaseToken.objects.filter(user=user).values_list('token', flat=True))
    if not tokens:
        logger.info(f'No tokens found for user: {user}')
        return False

    access_token = _get_access_token()
    url = (
        'https://iid.googleapis.com/iid/v1:batchAdd'
        if action == 'subscribe'
        else 'https://iid.googleapis.com/iid/v1:batchRemove'
    )

    resp = requests.post(
        url=url,
        headers={
            'Authorization': f'Bearer {access_token.token}',
            'Content-Type': 'application/json',
            "access_token_auth": "true",
        },
        json={
            'to': f'/topics/{topic}',
            'registration_tokens': tokens,
        },
    )

    try:
        resp_json = resp.json()
    except ValueError:
        resp_json = None
    not_found_tokens = []
    if resp.ok and resp_json and 'results' in resp_json:
        for idx, result in enumerate(resp_json['results']):
            if 'error' in result:
                error = result['error']
                if error == 'NOT_FOUND':
                    not_found_tokens.append(tokens[idx])
                    logger.warning(f'Token not found: {tokens[idx]}')
                else:
                    logger.warning(f'Error for token {tokens[idx]}: {error}')
            else:
                logger.info(f'Successfully {action} user {user} topic: {topic}')
                fcm_topic_subscription.status = DONE
                fcm_topic_subscription.save(update_fields=['status'])
                return
    else:
        logger.warning(
            f'Failed to {action} user {user} to topic: {topic} Response: {resp.text}-{resp}'
        )
    if not_found_tokens:
        FirebaseToken.objects.filter(token__in=not_found_tokens).delete()
    return False


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
        body['topic'] = f"/topics/{topic}"

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
    logger.info(f"fcm-resp--{resp}--{body}")

    if not resp.ok:
        logger.info(f"fcm-resp--{body}")
        logger.info(f"fcm-resp--{resp.status_code}")
        logger.info(f"fcm-resp--{resp.json()}")

    if resp.status_code == 404:
        from accounts.models import FirebaseToken
        data = resp.json()

        if data['error']['status'] == 'NOT_FOUND':
            FirebaseToken.objects.filter(token=token).delete()

    return resp.ok
