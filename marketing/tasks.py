import time
from collections import defaultdict
from datetime import timedelta, datetime

import requests
from celery import shared_task
from decouple import config

from accounting.models import PeriodicFetcher
from ledger.exceptions import FetchError
from ledger.utils.price import get_last_price, USDT_IRT
from marketing.models import AdsReport, CampaignPublisherReport, CampaignCost, CampaignInfo


def yektanet_requester(path: str, params: dict):
    url = 'https://api.yektanet.com/api/v1/external' + path
    header = {
        'Authorization': 'Token ' + config('YEKTANET_TOKEN')
    }
    resp = requests.get(url=url, params=params, headers=header, timeout=60)

    if not resp.ok:
        raise FetchError

    return resp.json()


UTM_TERM_PREFIX = {
    'native': 'yn_item_',
    'banner': 'yn_banner_',
    'mobile': 'yn_mob_',
}


def yektanet_ads_fetcher(start: datetime, end: datetime):
    # for ad_type in ('native', 'banner', 'push', 'mobile', 'video', 'universal'):

    start_date, end_date = str(start.astimezone().date()), str(end.astimezone().date())

    for ad_type in ('native', 'banner', 'mobile'):
        resp = yektanet_requester('/campaigns-ad-report/', params={
            'type': ad_type,
            'start_date': start_date,
            'end_date': end_date,
        })

        per_campaign_cost = defaultdict(int)

        usdt_price = get_last_price(USDT_IRT) or 60_000

        for data in resp:
            AdsReport.objects.update_or_create(
                created=start,
                type=ad_type,
                utm_campaign=data['utm_campaign'],
                utm_term=UTM_TERM_PREFIX.get(ad_type, '') + str(data['ad_id']),
                ad_id=data['ad_id'],
                campaign_id=data['campaign_id'],
                defaults={
                    'views': data['views'],
                    'clicks': data['clicks'],
                    'cost': data['cost'],
                }
            )

            per_campaign_cost[(data['campaign_id'], data['utm_campaign'])] += data['cost']

        for (campaign_id, utm_campaign), cost in per_campaign_cost.items():
            campaign, _ = CampaignInfo.objects.get_or_create(
                campaign_id=campaign_id,
                defaults={
                    'title': f'Yekanet {utm_campaign} (auto)',
                    'utm_source': 'yektanet',
                    'utm_campaign': utm_campaign
                }
            )

            CampaignCost.objects.update_or_create(
                campaign=campaign,
                created=start_date,
                defaults={
                    'cost_irt': cost,
                    'cost_usdt': cost / usdt_price,
                }
            )

        resp = yektanet_requester('/campaigns-publisher-report/', params={
            'type': ad_type,
            'start_date': start_date,
            'end_date': end_date,
        })

        for data in resp:
            CampaignPublisherReport.objects.update_or_create(
                created=start,
                type=ad_type,
                utm_campaign=data['utm_campaign'],
                utm_content=data['publisher_name'] or '',
                campaign_id=data['campaign_id'],
                publisher_id=data['publisher_id'],
                defaults={
                    'views': data['views'],
                    'clicks': data['clicks'],
                    'cost': data['cost'],
                }
            )



        time.sleep(2)


@shared_task()
def fill_ads_reports():
    PeriodicFetcher.repetitive_fetch(
        name='marketing-yektanet-ads',
        fetcher=yektanet_ads_fetcher,
        interval=timedelta(days=1)
    )
