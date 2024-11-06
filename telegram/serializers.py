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
        print('the whole context is: ', self.context)
        print("In serializer, the user is:", user)

        random_string = generate_and_store_user_key(user.id)
        print(f"Stored in Redis with key {random_string} and expiration {300} seconds")

        # Build the Telegram link with the random string
        bot_username = "amir_raastin_bot"
        telegram_link = f"https://t.me/{bot_username}?start={random_string}"
        print("Generated Telegram Link:", telegram_link)

        return telegram_link

        # access_token = SetPasswordAccessToken.for_user(user)
        # access_token.set_exp(lifetime=timedelta(minutes=60))
        #
        # token = generate_signed_token(user.id)
        # print('Token size: ', len(token), "this is the token: ", token)
        #
        # bot_username = "amir_raastin_bot"
        # telegram_link = f"https://t.me/{bot_username}?start={token}"
        # print("Generated Telegram Link:", telegram_link)
        #
        # return telegram_link

    class Meta:
        fields = ['telegram_link']
