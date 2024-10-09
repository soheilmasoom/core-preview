from django.core.validators import MinValueValidator
from django.db import models
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from simple_history.models import HistoricalRecords


class Network(models.Model):
    ETH = 'ETH'
    TRX = 'TRX'
    BSC = 'BSC'

    history = HistoricalRecords()

    symbol = models.CharField(max_length=16, unique=True, db_index=True)
    name = models.CharField(max_length=128, blank=True)

    can_withdraw = models.BooleanField(default=True)
    can_deposit = models.BooleanField(default=False)

    min_confirm = models.PositiveIntegerField(default=100, validators=[MinValueValidator(1)])
    unlock_confirm = models.PositiveIntegerField(default=0)

    explorer_link = models.CharField(max_length=128, blank=True)
    address_regex = models.CharField(max_length=128, blank=True)
    memo_regex = models.CharField(max_length=128, blank=True)

    deposit_need_memo = models.BooleanField(default=False)
    withdraw_allow_memo = models.BooleanField(default=False)
    memo_title_fa = models.CharField(max_length=64, default="آدرس تگ یا ممو")
    memo_name_fa = models.CharField(max_length=64, default="ممو")
    memo_name = models.CharField(max_length=64, default="memo")

    expected_confirmation_minutes = models.PositiveSmallIntegerField(default=10)

    def __str__(self):
        return self.symbol


class NetworkField(serializers.CharField):
    def to_representation(self, value: Network):
        if value:
            return value.symbol

    def to_internal_value(self, data: str):
        if not data:
            return
        else:
            return get_object_or_404(Network, symbol=data)
