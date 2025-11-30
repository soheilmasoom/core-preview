import datetime
import logging
from datetime import timedelta
from secrets import randbelow

import jdatetime
from django.utils import timezone

logger = logging.getLogger(__name__)

MINUTES = 60
HOUR = 60 * MINUTES
DAY = 24 * HOUR

PHONE_MAX_LENGTH = 16


def random_number(lower_bound, upper_bound):
    assert lower_bound < upper_bound, 'upper_bound should be greater than lower_bound'

    return lower_bound + randbelow(upper_bound - lower_bound)


def generate_random_code(n: int):
    code = random_number(10 ** (n - 1), 10 ** n)
    return code


def is_email(email: str):
    return '@' in email


def fifteen_minutes_later_datetime():
    now = timezone.now()
    fifteen_minutes = timedelta(seconds=15 * MINUTES)
    return now + fifteen_minutes


def gregorian_to_jalali_date(date: datetime.date):
    return jdatetime.date.fromgregorian(day=date.day, month=date.month, year=date.year)


def gregorian_to_jalali_date_str(date: datetime.date):
    return gregorian_to_jalali_date(date).strftime('%Y/%m/%d')


def gregorian_to_jalali_datetime(d: datetime):
    d = d.astimezone()
    return jdatetime.datetime.fromgregorian(
        year=d.year,
        month=d.month,
        day=d.day,
        hour=d.hour,
        minute=d.minute,
        second=d.second
    )


PERSIAN_DIGIT_MAP = {
    '0': '۰',
    '1': '۱',
    '2': '۲',
    '3': '۳',
    '4': '۴',
    '5': '۵',
    '6': '۶',
    '7': '۷',
    '8': '۸',
    '9': '۹',
}


def get_persian_number(num) -> str:
    return ''.join(map(lambda c: PERSIAN_DIGIT_MAP.get(c, c), str(num)))


def persian_timedelta(d: timedelta) -> str:
    parts = []

    if d.days > 0:
        parts.append(f'{get_persian_number(d.days)} روز')

    seconds = d.seconds
    hours = seconds // 3600
    seconds -= hours * 3600
    minutes = seconds // 60
    seconds -= minutes * 60

    if hours > 0:
        parts.append(f'{get_persian_number(hours)} ساعت')

    if minutes > 0:
        parts.append(f'{get_persian_number(minutes)} دقیقه')

    if d.days == 0 and d.seconds < 300:
        parts.append(f'{get_persian_number(seconds)} ثانیه')

    return ' و '.join(parts)


def timedelta_message(d: timedelta, ignore_seconds: bool = False) -> str:
    parts = []

    if d.days > 0:
        parts.append(f'{d.days} days')

    seconds = d.seconds
    hours = seconds // 3600
    seconds -= hours * 3600
    minutes = seconds // 60
    seconds -= minutes * 60

    if hours > 0:
        parts.append(f'{hours} hours')

    if minutes > 0:
        parts.append(f'{minutes} minutes')

    if not ignore_seconds:
        if d.days == 0 and d.seconds < 300:
            parts.append(f'{seconds} seconds')

    return ' and '.join(parts)


def gregorian_to_jalali_datetime_str(d: datetime):
    return gregorian_to_jalali_datetime(d).strftime('%Y/%m/%d %H:%M:%S')


def parse_positive_int(inp: str, default: int = None):
    try:
        num = int(inp)

        if num < 0:
            num = default
    except (ValueError, TypeError):
        num = default

    return num


def get_jalali_now():
    return gregorian_to_jalali_datetime_str(timezone.now())
