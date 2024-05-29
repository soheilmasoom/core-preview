import json
import logging
from typing import Tuple

import requests
from decouple import config
from oauth2client.service_account import ServiceAccountCredentials

from accounts.models import User

logger = logging.getLogger(__name__)


def _get_access_token() -> Tuple[str, str]:
    scopes = ['https://www.googleapis.com/auth/firebase.messaging']
    firebase_dict = json.loads(config('FIREBASE_SECRET_JSON', ''))

    credentials = ServiceAccountCredentials._from_parsed_json_keyfile(firebase_dict, scopes)
    access_token_info = credentials.get_access_token()

    return firebase_dict['project_id'], access_token_info.access_token


def send_push_notif_to_user(user: User, title: str, body: str, image: str = None, link: str = None):
    from accounts.models import FirebaseToken

    for firebase_token in FirebaseToken.objects.filter(user=user):
        send_push_notif(firebase_token.token, title, body, image, link)


def send_push_notif(token: str, title: str, body: str, image: str = None, link: str = None):
    notification = {
        "body": body,
        "title": title
    }

    if image:
        notification['image'] = image

    body = {
        "token": token,
        "notification": notification
    }

    if link:
        body['webpush'] = {
            'fcm_options': {
                'link': link
            }
        }

    project_id, access_token = _get_access_token()

    resp = requests.post(
        url=f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send',
        headers={
            'Authorization': 'Bearer ' + access_token,
            'Content-Type': 'application/json; UTF-8',
        },
        json={
            'message': body
        },
        timeout=10,
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
