from enum import Enum

from _base import settings
from django.contrib import admin


class ExchangeType(str, Enum):
    CRYPTO = 'CRYPTO'
    PRECIOUS_METALS = 'PRECIOUS_METALS'

    @property
    def is_crypto(self) -> bool:
        return self is ExchangeType.CRYPTO

    @property
    def is_precious_metals(self) -> bool:
        return self is ExchangeType.PRECIOUS_METALS


def admin_register_for_precious_metals_exchange(model):
    def decorator(admin_class):
        if settings.EXCHANGE_TYPE.is_precious_metals:
            return admin.register(model)(admin_class)
        return admin_class

    return decorator


def admin_register_for_crypto_exchange(model):
    def decorator(admin_class):
        if settings.EXCHANGE_TYPE.is_crypto:
            return admin.register(model)(admin_class)
        return admin_class

    return decorator
