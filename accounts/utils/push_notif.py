import logging
from typing import Optional

from accounts.models import User, FirebaseToken
from accounts.utils.firebase_service import firebase_service, PushNotificationPayload

logger = logging.getLogger(__name__)


def send_push_notif_to_user(
    user: User,
    title: str,
    body: str,
    image: Optional[str] = None,
    link: Optional[str] = None,
    data: Optional[dict] = None
) -> int:
    tokens = list(
        FirebaseToken.live_objects
        .filter(user=user)
        .values_list('token', flat=True)
    )
    
    if not tokens:
        logger.info(f"No active tokens found for user {user.id}")
        return 0
    
    payload = PushNotificationPayload(
        title=title,
        body=body,
        image=image,
        link=link,
        data=data
    )
    
    if len(tokens) == 1:
        result = firebase_service.send_to_token(tokens[0], payload)
        return 1 if result else 0
    else:
        result = firebase_service.send_multicast(tokens, payload)
        return result['success_count']


def send_push_notif_to_token(
    token: str,
    title: str,
    body: str,
    image: Optional[str] = None,
    link: Optional[str] = None,
    ttl: Optional[int] = None,
    collapse_key: Optional[str] = None,
    data: Optional[dict] = None
) -> Optional[str]:
    payload = PushNotificationPayload(
        title=title,
        body=body,
        image=image,
        link=link,
        data=data
    )
    
    return firebase_service.send_to_token(
        token=token,
        payload=payload,
        ttl=ttl,
        collapse_key=collapse_key
    )


def send_push_notif_to_topic(
    topic: str,
    title: str,
    body: str,
    image: Optional[str] = None,
    link: Optional[str] = None,
    ttl: Optional[int] = None,
    collapse_key: Optional[str] = None,
    data: Optional[dict] = None
) -> Optional[str]:
    payload = PushNotificationPayload(
        title=title,
        body=body,
        image=image,
        link=link,
        data=data
    )
    
    return firebase_service.send_to_topic(
        topic=topic,
        payload=payload,
        ttl=ttl,
        collapse_key=collapse_key
    )


def trigger_topic_subscriptions(pending_tokens):
    from accounts.utils.fcm_topic import fcm_topic_manager
    
    tokens = pending_tokens.tokens
    topic = pending_tokens.topic
    action = pending_tokens.action
    
    if action == pending_tokens.SUBSCRIBE:
        result = firebase_service.subscribe_to_topic(tokens, topic)
    else:
        result = firebase_service.unsubscribe_from_topic(tokens, topic)
    
    if result['success_count'] > 0:
        successful_tokens = [
            token for idx, token in enumerate(tokens)
            if idx < result['success_count']
        ]
        
        if successful_tokens:
            pending_tokens.tokens = successful_tokens
            fcm_topic_manager.remove_pending_tokens(pending_tokens)
    
    if result.get('errors'):
        invalid_tokens = []
        for error in result['errors']:
            idx = error.index
            if idx < len(tokens):
                invalid_tokens.append(tokens[idx])
        
        if invalid_tokens:
            fcm_topic_manager.cleanup_invalid_tokens(invalid_tokens)
    
    return result['success_count'] > 0
