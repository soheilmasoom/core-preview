import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def get_cache_func_key(func, *args, **kwargs) -> str:
    if func is not None:
        serialise = [func.__module__, func.__name__]
    else:
        serialise = []

    for arg in args:
        serialise.append(str(arg))

    for key, arg in kwargs.items():
        serialise.append(str(key))
        serialise.append(str(arg))

    key = hashlib.md5("".join(serialise).encode('utf-8')).hexdigest()

    return key


def cache_for(time: float = 600):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            key = get_cache_func_key(fn, *args, **kwargs)
            result = cache.get(key)

            if result is None:
                result = fn(*args, **kwargs)
                cache.set(key, result, time)

            return result
        return wrapper

    return decorator
