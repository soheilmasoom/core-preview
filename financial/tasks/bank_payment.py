import requests
from decouple import config


def update_jibimo_cash_ins():
    resp = requests.post('https://api.jibimo.com/v2/auth/token', headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }, json={
        'username': config('JIBIMO_USERNAME'),
        'password': config('JIBIMO_PASSWORD'),
        'secret_key': config('JIBIMO_SECRET_KEY'),
        'scopes': ['registered-user']
    })

    resp = resp.json()

    token = resp['token_type'] + ' ' + resp['access_token']

    resp = requests.get(
        'https://api.jibimo.com/v2/transactions/transaction?all&filters={\'type\':[\'Cash-In\'],%22status%22:\[%22Accepted%22\]\}&page=1&ac_id=369712&per_page=20',
        headers={
            'Authorization': token
        }
    )

    data_list = resp.json()['data']

