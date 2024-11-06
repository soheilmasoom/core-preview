import dataclasses
from typing import List, Union, Literal, Tuple

from django.conf import settings
from redis.client import Redis


__all__ = ('fcm_topic_manager', 'PendingTokens')


@dataclasses.dataclass
class PendingTokens:
    ACTIONS = SUBSCRIBE, UNSUBSCRIBE = 'sub', 'unsub'

    topic: str
    action: str
    tokens: List[str]


class FcmTopicManger:
    def __init__(self):
        self.redis = Redis.from_url(settings.FCM_CACHE_LOCATION, decode_responses=True)

    @classmethod
    def _get_topic_key(cls, topic: str, action: str) -> str:
        return f'fcm:{action}:{topic}'

    @classmethod
    def _get_topic_action_from_key(cls, key: str) -> Tuple[str, str]:
        action, topic = key.split(':')[1:]
        return topic, action

    def subscribe(self, topic: str, tokens: List[str]):
        self._add(topic=topic, action=PendingTokens.SUBSCRIBE, tokens=tokens)

    def unsubscribe(self, topic: str, tokens: List[str]):
        self._add(topic=topic, action=PendingTokens.UNSUBSCRIBE, tokens=tokens)

    def get_pending_tokens(self) -> Union[PendingTokens, None]:
        keys = self._get_keys()
        if not keys:
            return

        key = keys[0]

        topic, action = self._get_topic_action_from_key(key)

        tokens = self.redis.srandmember(key, 1000)

        return PendingTokens(
            action=action,
            topic=topic,
            tokens=tokens
        )

    def remove_pending_tokens(self, pending_tokens: PendingTokens):
        self._remove(
            topic=pending_tokens.topic,
            action=pending_tokens.action,
            tokens=pending_tokens.tokens
        )

    def cleanup_invalid_tokens(self, invalid_tokens: List[str]):
        if not invalid_tokens:
            return

        for key in self._get_keys():
            self.redis.srem(key, *invalid_tokens)

    def _add(self, topic: str, action: str, tokens: List[str]):
        if not tokens:
            return

        key = self._get_topic_key(topic, action)

        self.redis.sadd(key, *tokens)

        reverse_action = PendingTokens.SUBSCRIBE if action == PendingTokens.UNSUBSCRIBE else PendingTokens.UNSUBSCRIBE
        reverse_key = self._get_topic_key(topic, reverse_action)
        self.redis.srem(reverse_key, *tokens)

    def _remove(self, topic: str, action: str, tokens: List[str]):
        if not tokens:
            return

        key = self._get_topic_key(topic=topic, action=action)
        self.redis.srem(key, *tokens)

    def _get_keys(self) -> List[str]:
        return self.redis.keys('fcm:*')


fcm_topic_manager = FcmTopicManger()
