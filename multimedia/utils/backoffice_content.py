import requests
from django.conf import settings

def create_coin_content(coin_name):
    data = {
        'coinName': coin_name,
    }
    url = settings.BACKOFFICE_BASE_URL + '/api/content-creator/coin'
    resp = requests.post(url=url, data=data, timeout=60)
    return resp.status_code, resp.json(),


def update_coin_content(coin_name):
    data = {
        'coinName': coin_name,
    }
    url = settings.BACKOFFICE_BASE_URL + '/api/content-creator/coin'
    resp = requests.patch(url=url, data=data, timeout=60)
    return resp.status_code, resp.json(),


def get_coin_content(coin_name):
    url = settings.BACKOFFICE_BASE_URL + '/api/content-creator/coin/' + coin_name
    resp = requests.get(url=url, timeout=60)
    return resp.status_code, resp.json(),
