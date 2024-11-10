from typing import Union

from django.core.cache import caches

from accounts.models import User, SystemConfig
from ledger.utils.random import secure_uuid4

cache = caches['token']


class TelegramAuthKey:
    @classmethod
    def generate_new_start_link(cls, user: User) -> str:
        auth_key = cls._generate_new_auth_key(user)
        config = SystemConfig.get_system_config()
        return f"https://t.me/{config.telegram_bot_username}?start={auth_key}"

    @classmethod
    def _generate_new_auth_key(cls, user: User) -> str:
        auth_key = secure_uuid4().hex

        redis_key = f"telegram:{auth_key}"
        cache.set(redis_key, user.id, timeout=1800)

        return auth_key

    @classmethod
    def get_user(cls, auth_key: str) -> Union[User, None]:
        user_id = cache.get(f"telegram:{auth_key}")
        if user_id:
            return User.objects.filter(id=user_id).first()
