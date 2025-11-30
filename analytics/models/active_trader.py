from django.db import models


class ActiveTrader(models.Model):
    DAILY, WEEKLY, MONTHLY = 1, 7, 30
    PERIODS = (DAILY, WEEKLY, MONTHLY)

    created = models.DateField(db_index=True)
    period = models.SmallIntegerField(
        choices=((DAILY, 'daily'), (WEEKLY, 'weekly'), (MONTHLY, 'monthly'), )
    )

    active = models.PositiveSmallIntegerField()
    new = models.PositiveSmallIntegerField()
    churn = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('created', 'period')
