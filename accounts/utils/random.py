import random
import string


def get_random_str(k: int = 8):
    chars = random.choices(
        string.ascii_letters + string.digits,
        k=k
    )
    return "".join(chars)
