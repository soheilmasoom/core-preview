from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from ledger.utils.provider import get_provider_requester


@shared_task(queue='celery')
def populate_coins_info():
    fetch_key = 'coins_info_fetching'

    if cache.get(fetch_key):
        print('updating coins info ignored')
        return

    cache.set(fetch_key, 1, 60)
    coins_info = get_provider_requester().get_coins_info()

    cache.set('coins_info', {
        'exp': (timezone.now() + timedelta(minutes=5)).timestamp(),
        'data': coins_info
    }, timeout=72 * 3600)

    cache.delete(fetch_key)
