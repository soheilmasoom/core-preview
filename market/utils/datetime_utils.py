from datetime import timedelta, datetime


def ceil_date(date, **kwargs):
    round_to = timedelta(**kwargs).total_seconds()
    tzmin = date.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0)
    seconds = (date - tzmin).total_seconds()
    return datetime.fromtimestamp(date.timestamp() + round_to - seconds % round_to).astimezone()


def floor_date(date, **kwargs):
    round_to = timedelta(**kwargs).total_seconds()
    tzmin = date.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0)
    seconds = (date - tzmin).total_seconds()
    return datetime.fromtimestamp(date.timestamp() - seconds % round_to).astimezone()
