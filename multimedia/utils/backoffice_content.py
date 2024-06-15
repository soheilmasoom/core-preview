import requests
from django.conf import settings

class BackofficeContent:
    BASE_URL = settings.BACKOFFICE_BASE_URL
    headers={'Authorization': settings.BACKOFFICE_TOKEN}

    def create_coin_content(self, coin_name):
        data = {
            'coinName': coin_name,
        }
        url = self.BASE_URL + '/api/content-creator/coin'
        resp = requests.post(url=url, headers=self.headers, data=data, timeout=60)
        return resp.status_code, resp.json(),


    def update_coin_content(self, coin_name):
        data = {
            'coinName': coin_name,
        }
        url = self.BASE_URL + '/api/content-creator/coin'
        resp = requests.patch(url=url, headers=self.headers, data=data, timeout=60)
        return resp.status_code, resp.json(),


    def get_coin_content(self, coin_name):
        url = self.BASE_URL + '/api/content-creator/coin/' + coin_name
        resp = requests.get(url=url, headers=self.headers, timeout=60)
        return resp.status_code, resp.json(),
