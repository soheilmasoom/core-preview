import jwt
from datetime import timedelta
from django.conf import settings
from rest_framework import serializers
from accounts.authentication import SetPasswordAccessToken
from datetime import timedelta
import base64
from .utils.generate_signed_token import generate_signed_token
import redis
from decouple import config
import uuid
from .utils.redis import generate_and_store_user_key


class TelegramLinkSerializer(serializers.Serializer):
    telegram_link = serializers.SerializerMethodField()

    def get_telegram_link(self, obj):
        user = self.context.get('user')
        if not user:
            raise ValueError("User not found in context")

        random_string = generate_and_store_user_key(user.id)

        bot_username = "amir_raastin_bot"
        telegram_link = f"https://t.me/{bot_username}?start={random_string}"

        return telegram_link

    class Meta:
        fields = ['telegram_link']
