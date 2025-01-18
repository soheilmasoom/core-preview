from datetime import datetime


def parse_datetime(date_str: str) -> datetime:
    if '.' in date_str:
        f = '%Y-%m-%dT%H:%M:%S.%f%z'
    else:
        f = '%Y-%m-%dT%H:%M:%S%z'

    return datetime.strptime(date_str, f)
