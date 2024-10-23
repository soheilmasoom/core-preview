import logging
import random
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Notification, Account, User
from ledger.models import Prize, Asset
from ledger.utils.fields import get_amount_field, get_created_field
from ledger.utils.precision import humanize_number
from ledger.utils.price import get_last_price
from ledger.utils.wallet_pipeline import WalletPipeline
from multimedia.storage import PublicMediaStorage

logger = logging.getLogger(__name__)


class MissionJourney(models.Model):
    name = models.CharField(max_length=64, unique=True)

    active = models.BooleanField(default=True)
    default = models.BooleanField(default=False)

    title = models.CharField(max_length=1024, blank=True)
    description = models.CharField(max_length=1024, blank=True)
    logo = models.ImageField(blank=True, null=True, storage=PublicMediaStorage(), upload_to='missions/logo/')

    def __str__(self):
        return self.name

    @classmethod
    def get_by_promotion(cls, promotion: str) -> 'MissionJourney':
        journey = MissionJourney.objects.filter(name=promotion, active=True).first()
        if not journey:
            journey = MissionJourney.objects.filter(active=True, default=True).first()

        return journey

    def save(self, *args, **kwargs):
        self.name = slugify(self.name)
        super(MissionJourney, self).save(*args, **kwargs)


class MissionDigest(models.Model):
    journey = models.ForeignKey(MissionJourney, on_delete=models.CASCADE, related_name='digests')
    order = models.PositiveSmallIntegerField(default=0)

    title = models.CharField(max_length=1024, blank=True)
    description = models.CharField(max_length=1024, blank=True)

    class Meta:
        ordering = ('order', 'id')


class MissionTemplate(models.Model):
    journey = models.ForeignKey(MissionJourney, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    expiration = models.DateTimeField(null=True, blank=True, db_index=True)

    def achievable(self, account: Account):
        if not self.achievement.achieved(account):
            return self.finished(account)

    def finished(self, account: Account):
        tasks = self.task_set.all()
        if not tasks:
            return True

        return all([task.finished(account) for task in tasks])

    def get_active_task(self, account: Account) -> 'Task':
        for task in self.task_set.all():
            if not task.finished(account):
                return task

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return self.name


class Achievement(models.Model):
    NORMAL, MYSTERY_BOX = 'normal', 'mystery_box'

    mission = models.OneToOneField(MissionTemplate, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True)
    amount = get_amount_field()
    voucher = models.BooleanField(default=False)

    @property
    def type(self):
        if self.asset:
            return self.NORMAL
        else:
            return self.MYSTERY_BOX

    def get_prize_achievement_message(self, prize: Prize):

        if not self.asset:
            template = 'جعبه شانس به شما تعلق گرفت. برای دریافت آن، کلیک کنید.'
        elif not self.voucher:
            template = 'جایزه {amount} {symbol} به شما تعلق گرفت. برای دریافت، کلیک کنید.'.format(
                amount=humanize_number(prize.amount),
                symbol=self.asset.name_fa
            )
        else:
            template = 'جایزه تخفیف کارمزد تا سقف {amount} {symbol} به شما تعلق گرفت.'.format(
                amount=humanize_number(prize.amount),
                symbol=self.asset.name_fa
            )

        return template

    def achieved(self, account: Account):
        return Prize.objects.filter(account=account, achievement=self).exists()

    def get_mystery_prize(self):
        rand = random.randint(1, 100)

        if rand <= 1:
            return {'coin': 'PEPE', 'amount': 2_000_000}
        elif rand <= 6:
            return {'coin': 'SHIB', 'amount': 100_000}
        elif rand <= 41:
            return {'coin': 'LUNC', 'amount': 2000}
        else:
            return {'coin': 'USDT', 'amount': 10, 'voucher': True}

    def achieve_prize(self, account: Account):
        value = 0

        voucher_expiration = None

        asset = self.asset
        amount = self.amount
        voucher = self.voucher
        auto_redeem = voucher

        if voucher:
            voucher_expiration = timezone.now() + timedelta(days=30)

        if not asset:
            mystery = self.get_mystery_prize()
            asset = Asset.objects.get(symbol=mystery['coin'])
            amount = mystery['amount']
            voucher = mystery.get('voucher', False)
            auto_redeem = False

            if voucher:
                voucher_expiration = timezone.now() + timedelta(days=7)

        if not voucher:
            price = get_last_price(Asset.SHIB + Asset.USDT) or 0
            value = amount * price

        with WalletPipeline() as pipeline:
            prize, created = Prize.objects.get_or_create(
                account=account,
                achievement=self,
                defaults={
                    'amount': amount,
                    'asset': asset,
                    'value': value,
                    'voucher_expiration': voucher_expiration
                }
            )

            if auto_redeem:
                prize.build_trx(pipeline)

            if created:
                title = 'دریافت جایزه'

                Notification.send(
                    recipient=account.user,
                    title=title,
                    message=self.get_prize_achievement_message(prize),
                    level=Notification.SUCCESS,
                    link='/account/tasks'
                )

    def is_mystery_box(self):
        return not bool(self.asset)

    def __str__(self):
        if self.is_mystery_box():
            prize = 'mysterybox'
        else:
            kind = ''
            if self.voucher:
                kind = ' voucher'
            prize = f'{self.amount} {self.asset}{kind}'

        return f'{self.mission} ({prize})'


class Task(models.Model):
    TYPES = VERIFY_LEVEL2, DEPOSIT, DEPOSIT_FROM_NOW, TRADE, TRADE_FROM_NOW, REFERRAL, SET_EMAIL = \
        'verify_level2', 'deposit', 'deposit_from_now', 'trade', 'weekly_trade', 'referral', 'set_email'

    BOOL, NUMBER = 'bool', 'number'

    mission = models.ForeignKey(MissionTemplate, on_delete=models.CASCADE)
    scope = models.CharField(max_length=16, choices=[(s, s) for s in TYPES])

    order = models.PositiveSmallIntegerField(default=0)
    type = models.CharField(max_length=8, default=NUMBER, choices=((BOOL, BOOL), (NUMBER, NUMBER)))
    max = models.PositiveIntegerField(default=1)

    title = models.CharField(max_length=32)
    link = models.CharField(max_length=32)
    app_link = models.CharField(max_length=256, default='')
    description = models.CharField(max_length=512)
    level = models.CharField(max_length=8, choices=Notification.LEVEL_CHOICES, default=Notification.WARNING)

    def get_goal_type(self):
        from gamify.goal_types import GOAL_TYPES

        for gt in GOAL_TYPES:
            if gt.name == self.scope:
                return gt(self)
        else:
            raise NotImplementedError

    def get_progress_percent(self, account: Account) -> int:
        _progress = self.get_goal_type().get_progress(account)

        if self.type == self.BOOL:
            if _progress:
                return 100
            else:
                return 0
        else:
            return max(min(int(_progress / self.max * 100), 100), 0)

    def finished(self, account: Account):
        progress = self.get_progress_percent(account)
        logger.info('checking task progress for %s on %s is %s' % (account, self, progress))
        return progress == 100

    class Meta:
        ordering = ('order', )

    def __str__(self):
        return '%s / %s' % (self.mission.name, self.type)


class UserMission(models.Model):
    created = get_created_field()
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    mission = models.ForeignKey(MissionTemplate, on_delete=models.CASCADE)
    finished = models.BooleanField(default=False)

    def __str__(self):
        return '%s %s' % (self.user, self.mission)

    @property
    def expired(self):
        if not self.mission.expiration:
            return False

        return self.mission.expiration < timezone.now()

    class Meta:
        unique_together = ('user', 'mission')

    def check_achievements(self):
        from gamify.utils import check_prize_achievements
        check_prize_achievements(account=self.user.get_account())
