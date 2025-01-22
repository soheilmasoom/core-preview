from django.db import models


class EventTracker(models.Model):
    TRADE, OTC_TRADE, TRADE_REVENUE = 'trade', 'otc_trade', 'revenue'
    TRANSFER, FIAT_WITHDRAW, PAYMENT = 'transfer', 'fiat_withdraw', 'payment'
    USER, LOGIN, TRAFFIC_SOURCE = 'user', 'login', 'traffic_source'
    PRIZE, STAKING, WALLET, TRANSACTION = 'prize', 'staking', 'wallet', 'transaction'

    TYPES = TRADE, OTC_TRADE, TRADE_REVENUE, TRANSFER, FIAT_WITHDRAW, PAYMENT, USER, LOGIN, TRAFFIC_SOURCE, \
            PRIZE, STAKING, WALLET, TRANSACTION

    created = models.DateField(auto_now_add=True)
    updated = models.DateField(auto_now=True)
    last_id = models.IntegerField(default=0)
    type = models.CharField(
        max_length=20,
        choices=[(t, t) for t in TYPES],
        unique=True
    )
