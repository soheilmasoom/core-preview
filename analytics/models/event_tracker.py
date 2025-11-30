from django.db import models


class EventTracker(models.Model):
    TRADE, OTC_TRADE = 'trade', 'otc_trade'
    TRANSFER, FIAT_WITHDRAW, PAYMENT = 'transfer', 'fiat_withdraw', 'payment'
    USER, LOGIN, TRAFFIC_SOURCE = 'user', 'login', 'traffic_source'
    PRIZE, STAKING, WALLET, TRANSACTION = 'prize', 'staking', 'wallet', 'transaction'

    created = models.DateField(auto_now_add=True)
    updated = models.DateField(auto_now=True)
    last_id = models.IntegerField(default=0)
    type = models.CharField(
        max_length=20,
        choices=[(TRADE, TRADE), (OTC_TRADE, OTC_TRADE), (TRANSFER, TRANSFER), (FIAT_WITHDRAW, FIAT_WITHDRAW),
                 (PAYMENT, PAYMENT), (USER, USER), (LOGIN, LOGIN), (TRAFFIC_SOURCE, TRAFFIC_SOURCE),
                 (PRIZE, PRIZE), (STAKING, STAKING), (WALLET, WALLET), (TRANSACTION, TRANSACTION)],
        unique=True
    )
