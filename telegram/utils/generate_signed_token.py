import hmac
import hashlib
import base64
from datetime import timedelta, datetime
from decouple import config


HMAC_SECRET_KEY = config('HMAC_SECRET_KEY').encode('utf-8')

def generate_signed_token(user_id):
    user_id_bytes = str(user_id).encode()

    signature = hmac.new(HMAC_SECRET_KEY, user_id_bytes, hashlib.sha256).digest()

    encoded_signature = base64.urlsafe_b64encode(signature).decode()

    token = f"{str(user_id)}_{encoded_signature}"

    full_token = f"{token}"

    return full_token
