from datetime import datetime, timedelta, date
from typing import Union

from django.utils import timezone

from accounts.models import User


def is_weekday(d: Union[date, datetime]) -> bool:
    return d.weekday() in (3, 4)
