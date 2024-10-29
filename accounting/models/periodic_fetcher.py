import logging
from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone

from ledger.exceptions import FetchError

logger = logging.getLogger(__name__)


class PeriodicFetcher(models.Model):
    name = models.CharField(max_length=64, unique=True)
    end = models.DateTimeField()

    @classmethod
    def get_next_range(cls, name: str, interval: timedelta):
        f = PeriodicFetcher.objects.filter(name=name).first()
        now = timezone.now().astimezone()

        if f:
            start = f.end
        else:
            start = now.replace(microsecond=0, second=0, minute=0, hour=0) - interval

        end = start + interval

        if end <= now:
            return start, end
        else:
            return

    @classmethod
    def confirm_range(cls, name: str, end: datetime):
        PeriodicFetcher.objects.update_or_create(
            name=name,
            defaults={
                'end': end
            }
        )

    @classmethod
    def repetitive_fetch(cls, name: str, fetcher, interval: timedelta, iterations: int = 100):
        for i in range(iterations):
            logger.info('fetching %s data' % name)

            _range = PeriodicFetcher.get_next_range(name, interval=interval)
            if not _range:
                return

            start, end = _range

            logger.info('   fetching %s data (%s, %s)' % (name, start.astimezone(), end.astimezone()))

            try:
                fetcher(start, end)
            except FetchError:
                logger.info('   Error in fetching %s data (%s, %s)!' % (name, start.astimezone(), end.astimezone()))
                return

            PeriodicFetcher.confirm_range(name, end)

    def __str__(self):
        return '%s %s' % (self.name, self.end)
