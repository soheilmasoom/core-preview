from django.db.models import Sum, F

from django.db.models import Sum, F

from accounts.models import Account, User
from financial.models import Payment
from gamify.models import Task, UserMission
from ledger.models import Transfer, OTCTrade
from ledger.utils.fields import DONE
from market.models import Trade


class BaseGoalType:
    name = ''

    def __init__(self, task):
        self.task = task

    def get_progress(self, account: Account):
        raise NotImplementedError


class VerifyLevel2Goal(BaseGoalType):
    name = Task.VERIFY_LEVEL2

    def get_progress(self, account: Account):
        return account.user.level > User.LEVEL1


class DepositGoal(BaseGoalType):
    name = Task.DEPOSIT

    def get_progress(self, account: Account):
        fiat_deposit = Payment.objects.filter(
            status=DONE,
            user=account.user
        ).aggregate(sum=Sum('amount'))['sum'] or 0

        if fiat_deposit >= self.task.max:
            return fiat_deposit

        crypto_deposit = Transfer.objects.filter(
            wallet__account=account,
            deposit=True,
            status=DONE
        ).aggregate(sum=Sum('irt_value'))['sum'] or 0

        return fiat_deposit + crypto_deposit


class TradeGoal(BaseGoalType):
    name = Task.TRADE

    def get_progress(self, account: Account):
        return account.trade_volume_irt


class WeeklyTradeGoal(BaseGoalType):
    name = Task.WEEKLY_TRADE

    def get_progress(self, account: Account):
        expiration = self.task.mission.expiration
        user_mission = UserMission.objects.get(mission=self.task.mission, user=account.user)

        otc_val = OTCTrade.objects.filter(
            otc_request__account=account,
            status=OTCTrade.DONE,
            created__range=(user_mission.created, expiration)
        ).aggregate(
            val=Sum(F('otc_request__amount') * F('otc_request__price') * F('otc_request__base_irt_price'))
        )['val'] or 0

        trade_val = Trade.objects.filter(
            account=account,
            created__range=(user_mission.created, expiration),
        ).aggregate(
            val=Sum(F('amount') * F('price') * F('base_irt_price'))
        )['val'] or 0

        return otc_val + trade_val


class ReferralGoal(BaseGoalType):
    name = Task.REFERRAL

    def get_progress(self, account: Account):
        return account.get_invited_count()


class SetEmailGoal(BaseGoalType):
    name = Task.SET_EMAIL

    def get_progress(self, account: Account):
        return bool(account.user.email)


GOAL_TYPES = [VerifyLevel2Goal, DepositGoal, TradeGoal, ReferralGoal, SetEmailGoal, WeeklyTradeGoal]
