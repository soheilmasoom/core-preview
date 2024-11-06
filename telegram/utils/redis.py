import uuid
from django.conf import settings
from decouple import config
import redis


REDIS_EXPIRATION_TIME = 3000
LOCAL_REDIS_URL = config('LOCAL_REDIS_URL', default='redis://127.0.0.1:6379')
redis_telegram = redis.from_url(LOCAL_REDIS_URL)

def generate_and_store_user_key(user_id):
    random_string = str(uuid.uuid4())
    redis_key = f"user_key:{random_string}"

    redis_telegram.setex(redis_key, REDIS_EXPIRATION_TIME, user_id)

    return random_string

def get_user_key(random_string):
    return redis_telegram.get(f"user_key:{random_string}")

def delete_user_key(random_string):
    redis_telegram.delete(f"user_key:{random_string}")