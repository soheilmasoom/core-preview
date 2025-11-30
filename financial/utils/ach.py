from datetime import datetime, date, timedelta
import json

from accounts.utils.validation import gregorian_to_jalali_date

with open('financial/data/holidays.json') as f:
    _holidays_dict = json.load(f)


def is_holiday(d: date):
    jalali = str(gregorian_to_jalali_date(d)).replace('-', '/')
    return _holidays_dict[jalali]


def next_non_holiday_day(d: date):
    for i in range(1, 14):
        d = d + timedelta(days=1)

        if not is_holiday(d):
            return d

    raise Exception('no non holiday date found after today')


def date_to_datetime(d: date, time: str):
    hour, minute = time_to_parts(time)
    return datetime(year=d.year, month=d.month, day=d.day, hour=hour, minute=minute).astimezone()


def get_time(d: datetime) -> str:
    return '%s:%s' % (d.hour, d.minute)


def time_to_parts(time: str) -> tuple:
    return tuple(map(int, time.split(':')))


def next_ach_clear_time(now: datetime = None) -> datetime:
    if not now:
        now = datetime.now().astimezone()

    now_date = now.date()

    if is_holiday(now_date):
        return date_to_datetime(next_non_holiday_day(now_date), '4:45')

    mapping = {
        ('0:0', '2:44'): ('4:45', 'today'),
        ('2:45', '9:44'): ('11:45', 'today'),
        ('9:45', '12:44'): ('14:45', 'today'),
        ('12:45', '17:44'): ('19:45', 'today'),
        ('17:45', '23:59'): ('4:45', 'next'),
    }

    time = get_time(now)

    for (start, end), (receive, receive_day) in mapping.items():
        if time_to_parts(start) <= time_to_parts(time) <= time_to_parts(end):
            ach_time = receive

            if receive_day == 'next':
                ach_date = next_non_holiday_day(now_date)
            else:
                ach_date = now_date

            return date_to_datetime(ach_date, ach_time)
