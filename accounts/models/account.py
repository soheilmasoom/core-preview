from decimal import Decimal
from typing import Union

from django.conf import settings
from django.db import models
from django.db.models import UniqueConstraint, Q, Sum
from django.utils import timezone

from ledger.utils.external_price import BUY
from ledger.utils.fields import get_amount_field


class Account(models.Model):
    SYSTEM = 's'
    OUT = 'o'
    ORDINARY = None

    TYPE_CHOICES = ((SYSTEM, 'system'), (OUT, 'out'), (ORDINARY, 'ordinary'))

    name = models.CharField(max_length=16, blank=True)

    user = models.OneToOneField('User', on_delete=models.CASCADE, null=True, blank=True)

    type = models.CharField(
        max_length=1,
        choices=TYPE_CHOICES,
        blank=True,
        null=True,
    )

    primary = models.BooleanField(default=True)

    margin_alerting = models.BooleanField(default=False)

    referred_by = models.ForeignKey(
        to='accounts.Referral',
        on_delete=models.SET_NULL,
        related_name='referred_accounts',
        null=True, blank=True
    )

    trade_volume_irt = models.PositiveBigIntegerField(default=0)

    bookmark_market = models.ManyToManyField("market.PairSymbol")
    bookmark_assets = models.ManyToManyField("ledger.Asset")

    owned = models.BooleanField(default=False)

    custom_maker_fee = get_amount_field(null=True)
    custom_taker_fee = get_amount_field(null=True)
    custom_max_margin_leverage = models.SmallIntegerField(null=True, blank=True)

    increase_fiat_withdraw_fee = models.BooleanField(default=False)

    def is_system(self) -> bool:
        return self.type == self.SYSTEM

    def is_ordinary_user(self) -> bool:
        # be careful about new market maker account, should be ordinary if dont want to hedge in Core
        return not bool(self.type)

    def get_max_margin_leverage(self):
        from accounts.models import SystemConfig
        sys_config = SystemConfig.get_system_config()
        return self.custom_max_margin_leverage or sys_config.max_margin_leverage

    @classmethod
    def system(cls) -> 'Account':
        return Account.objects.get(type=cls.SYSTEM, primary=True)

    @classmethod
    def out(cls) -> 'Account':
        return Account.objects.get(type=cls.OUT)

    def is_proxy_trader(self, symbol_name: str):
        from accounts.models import SystemConfig

        return self.id == settings.OTC_ACCOUNT_ID \
               or (SystemConfig.get_system_config().hedge_irt_by_internal_market and symbol_name == 'USDTIRT' and self.id == settings.MARKET_MAKER_ACCOUNT_ID)

    def get_voucher_wallet(self):
        from ledger.models import Wallet
        from ledger.models import Asset

        return Wallet.objects.filter(
            account=self,
            asset__symbol=Asset.USDT,
            market=Wallet.VOUCHER,
            expiration__gte=timezone.now(),
            balance__gt=0
        ).first()

    def __str__(self):
        if self.type == self.SYSTEM:
            name = 'system'

            if self.name:
                name += ' - %s' % self.name

            return name

        elif self.type == self.OUT:
            return 'out'
        else:
            return str(self.user)

    def get_total_balance_usdt(self):
        from ledger.models import Wallet, Asset
        from ledger.utils.price import get_last_price

        wallets = dict(Wallet.objects.filter(
            account=self
        ).exclude(
            balance=0
        ).exclude(
            market=Wallet.VOUCHER
        ).values('asset__symbol').annotate(
            amount=Sum('balance')
        ).values_list('asset__symbol', 'amount'))

        total = Decimal('0')

        for coin, balance in wallets.items():
            price = get_last_price(coin + Asset.USDT) or 0
            balance = balance * price

            total += balance

        return total

    def get_total_balance_irt(self, market: str = None, side: str = BUY):
        from ledger.models import Wallet, Asset
        from ledger.utils.price import get_last_price

        wallets = Wallet.objects.filter(account=self).prefetch_related('asset')

        if market:
            wallets = wallets.filter(market=market)
        else:
            wallets = wallets.exclude(market=Wallet.VOUCHER)

        total = Decimal('0')

        for wallet in wallets:
            if wallet.balance == 0:
                continue

            price = get_last_price(wallet.asset.symbol + Asset.IRT) or 0
            balance = wallet.balance * price

            if balance:
                total += balance

        return total

    def save(self, *args, **kwargs):
        super(Account, self).save(*args, **kwargs)

        if self.type and self.user and self.primary:
            raise Exception('User connected to system account')

    def print(self):
        from ledger.models import Wallet
        wallets = Wallet.objects.filter(account=self).order_by('market')

        print('Wallets')

        for w in wallets:
            print('%s %s %s: %s' % (w.account, w.asset.symbol, w.market, w.get_free()))

        print()

    def get_invited_count(self):
        return int(Account.objects.filter(referred_by__owner=self).count())

    def airdrop(self, asset, amount: Union[Decimal, int]):
        wallet = asset.get_wallet(self)
        wallet.airdrop(amount)

    @classmethod
    def get_for(cls, user):
        if not user.id or user.is_anonymous:
            return Account()
        else:
            account, _ = Account.objects.get_or_create(user=user)
            return account

    def has_zero_balance(self) -> bool:
        from ledger.models.wallet import Wallet
        return not Wallet.objects.filter(
                ~Q(balance=Decimal(0)),
                account=self,
                ).exists()
    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["type"],
                name="unique_account_type_primary",
                condition=Q(primary=True),
            )
        ]
