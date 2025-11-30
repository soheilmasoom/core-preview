from datetime import timedelta, datetime

import pytz
from celery import shared_task

from accounting.models import Vault, PeriodicFetcher, ProviderIncome
from ledger.utils.provider import get_provider_requester


@shared_task()
def fill_provider_incomes():

    for v in Vault.objects.filter(type=Vault.PROVIDER, market=Vault.FUTURES):

        def income_fetcher(start: datetime, end: datetime):
            incomes = get_provider_requester().get_income_history(
                profile_id=v.key,
                start=start,
                end=end,
            )

            for income in incomes:
                ProviderIncome.objects.get_or_create(
                    tran_id=income['tranId'],
                    defaults={
                        'symbol': income['symbol'],
                        'income_type': income['incomeType'],
                        'income_date': datetime.utcfromtimestamp(income['time'] // 1000).replace(tzinfo=pytz.UTC),
                        'income': income['income'],
                        'coin': income['asset'],
                    }
                )

        name = 'vault-income-%s' % v.key

        PeriodicFetcher.repetitive_fetch(
            name=name,
            fetcher=income_fetcher,
            interval=timedelta(hours=1)
        )
