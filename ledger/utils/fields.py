from decimal import Decimal
from typing import Union
from uuid import uuid4

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import CharField
from rest_framework import serializers

from ledger.utils.cache import cache_for
from ledger.utils.precision import normalize_fraction, AMOUNT_PRECISION

PROCESS, PENDING, CANCELED, DONE, REFUND = 'process', 'pending', 'canceled', 'done', 'refund'
INIT, REJECTED, VERIFIED = 'init', 'rejected', 'verified'

STATUS_CHOICES = (INIT, INIT), (PROCESS, PROCESS), (PENDING, PENDING), (CANCELED, CANCELED), (DONE, DONE)


def get_amount_field(default: Union[Decimal, int] = None, max_digits: int = None, decimal_places: int = None,
                     null: bool = False, validators: tuple = (MinValueValidator(0),), verbose_name: str = None):
    if validators is None:
        validators = [MinValueValidator(0)]

    kwargs = {
        'max_digits': max_digits or 30,
        'decimal_places': decimal_places or AMOUNT_PRECISION,
        'validators': validators,
        'blank': null,
        'null': null,
        'verbose_name': verbose_name
    }

    if default is not None:
        kwargs['default'] = default

    return models.DecimalField(**kwargs)


def get_serializer_amount_field(**kwargs):
    return SerializerDecimalField(
        max_digits=30,
        decimal_places=8,
        min_value=0,
        **kwargs,
    )


def get_status_field(default=PENDING):
    return models.CharField(
        default=default,
        max_length=8,
        db_index=True,
        choices=[
            (INIT, INIT), (PROCESS, PROCESS), (PENDING, PENDING), (CANCELED, CANCELED), (DONE, DONE),
            (REFUND, REFUND)
        ]
    )


def get_verify_status_field(default=INIT):
    return models.CharField(
        default=INIT,
        max_length=8,
        choices=[(INIT, 'init'), (PENDING, 'pending'), (REJECTED, 'rejected'), (VERIFIED, 'verified')]
    )


def get_group_id_field(db_index: bool = False, null: bool = False, default=uuid4, unique: bool = False):
    return models.UUIDField(default=default, db_index=db_index, null=null, blank=null, unique=unique)


def get_address_field():
    return CharField(max_length=256)


def get_created_field():
    return models.DateTimeField(auto_now_add=True)


def get_modified_field():
    return models.DateTimeField(auto_now=True)


class SerializerDecimalField(serializers.DecimalField):
    def to_representation(self, data: Decimal):
        if data is None:
            return None

        if not isinstance(data, Decimal):
            data = Decimal(str(data).strip())

        return '{:f}'.format(normalize_fraction(data))


@cache_for(time=600)
def get_irt_market_asset_symbols():
    from market.models import PairSymbol
    from ledger.models import Asset
    return set(PairSymbol.objects.select_related('base_asset').filter(
        enable=True,
        base_asset__symbol=Asset.IRT
    ).values_list('asset__symbol', flat=True))
