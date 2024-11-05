import dataclasses
import json
import logging
import time
from collections import defaultdict
from typing import Set, Union

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

    fcm_topic_manager.cleanup_invalid_tokens(invalid_tokens)

    return True


def send_push_notif_to_user(user: User, title: str, body: str, image: str = None, link: str = None):
    from accounts.models import FirebaseToken

    for firebase_token in FirebaseToken.live_objects.filter(user=user):
        send_push_notif(title, body, firebase_token.token, image, link)


def send_push_notif(title: str, body: str, token: str = None, image: str = None, link: str = None, topic: str = None,
                    ttl: int = None, collapse_key: str = None) -> Union[str, None]:

    assert topic or token

    notification = {
        "body": body,
        "title": title
    }

    if image:
        notification['image'] = image

    android_data = {}
    web_push_data = defaultdict(dict)

    body = {
        "notification": notification,
    }

    if token:
        body['token'] = token
    else:
        body['topic'] = topic

    if link:
        web_push_data['fcm_options']['link'] = link

    if ttl:
        android_data['ttl'] = f'{ttl}s'
        web_push_data['headers']['TTL'] = str(ttl)

    if collapse_key:
        android_data['collapse_key'] = collapse_key

    if web_push_data:
        body['webpush'] = dict(web_push_data)

    if android_data:
        body['android'] = android_data

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

    success = resp.ok
    data = resp.json()

    if token:
        logger.info(f"Sending single push notif to token={token} {'succeeded' if success else 'failed'} ({data})")
    else:
        logger.info(f"Sending bulk push notif to topic={topic} {'succeeded' if success else 'failed'} ({data})")

    if resp.status_code == 404:
        from accounts.models import FirebaseToken
        error = data['error']['status']
        if error in ['NOT_FOUND', 'INVALID_ARGUMENT', 'PERMISSION_DENIED']:
            FirebaseToken.live_objects.filter(token=token).update(active=False, error=error)

    if resp.ok:
        return data['name']


def get_fcm_token_registered_coins(fcm_token: FirebaseToken) -> Union[None, Set[str]]:
    access_token = _get_access_token()

    resp = requests.get(
        url=f'https://iid.googleapis.com/iid/info/{fcm_token.token}?details=true',
        headers={
            'Authorization': f'Bearer {access_token.token}',
            'Content-Type': 'application/json',
            "access_token_auth": "true",
        },
    )

    if not resp.ok:
        return None

    data = resp.json()

    return set(map(lambda x: x[13:].upper(), data['rel']['topics'].keys()))


def get_user_registered_coins(user: User) -> Set[str]:
    coins = None

    for fcm_token in user.fcm_tokens.filter(active=True):
        _coins = get_fcm_token_registered_coins(fcm_token)
        if _coins is None:
            continue

        if coins is None:
            coins = _coins
        else:
            coins = coins & _coins

    return coins or set()


def get_asset_alert_mismatch(user: User) -> bool:
    from ledger.models import AssetAlert

    if not user.fcm_tokens.filter(active=True):
        logger.info(f'Alert mismatch OK for {user} due to no fcm token exists')
        return True

    subscribed_coins = get_user_registered_coins(user)
    alert_coins = set(AssetAlert.objects.filter(user=user).values_list('asset__symbol', flat=True))

    if subscribed_coins == alert_coins:
        logger.info(f'Alert mismatch OK for {user} in {subscribed_coins}')

        return True

    else:
        logger.info(f'Alert mismatch found for {user}')
        logger.info(f'   Missing subscriptions: {alert_coins - subscribed_coins}')
        logger.info(f'   Missing unsubscriptions: {subscribed_coins - alert_coins}')

        return False
