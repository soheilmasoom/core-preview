import requests
from django.conf import settings


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_ip_data(ip):
    if settings.DEBUG_OR_TESTING:
        return {}

    try:
        resp = requests.post(
            url='http://ip-api.com/json/{ip}'.format(ip=ip),
            timeout=1
        )
        return resp.json()

    except:
        return {}
