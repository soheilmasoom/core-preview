import dataclasses
from datetime import timedelta
from decimal import Decimal
from typing import List

from django.conf import settings
from django.db.models import Sum, Max
from django.utils import timezone

from accounts.admin_guard.utils.html import get_table_html
from accounts.models import Account, User, SystemConfig
from accounts.models.login_activity import LoginActivity
from accounts.utils.hijack import get_hijacker_id
from financial.models import Payment
from ledger.models import Transfer, Wallet, NetworkAsset
from ledger.utils.external_price import BUY
from ledger.utils.fields import CANCELED
from ledger.utils.precision import humanize_number

FATA_SAFE_DEBT_IRT_VALUE = -3_000_000
FATA_RISKY_DEBT_IRT_VALUE = -10_000_000

SAFE_DAILY_WITHDRAW_VALUE = 400
SAFE_MONTHLY_WITHDRAW_VALUE = 40_000

SAFE_CURRENT_DEPOSITS_VALUE = 500
SAFE_CURRENT_TRANSFERS_COUNT = 12


def auto_withdraw_verify(transfer: Transfer) -> bool:
    assert not transfer.deposit

    if transfer.wallet.account.user.withdraw_limit_whitelist:
        return True

    common_system_risks = get_common_system_risks(transfer.wallet.account)

    system_risks = get_withdraw_system_risks(transfer)
    fata_risks = get_withdraw_fata_risks(transfer)

    risks = [*common_system_risks, *system_risks, *fata_risks]

    if risks:
        transfer.risks = list(map(dataclasses.asdict, risks))
        transfer.save(update_fields=['risks'])

        if fata_risks and fata_risks[0].whitelist:
            risks = system_risks

    return not bool(risks)


@dataclasses.dataclass
class RiskFactor:
    FIAT_DEBT_RISK = 'fiat-debt-risk'
    NEW_RECIPIENT_ADDRESS = 'new-recipient-address'
    MULTIPLE_DEVICES = 'multiple-devices'

    DAY_HIGH_WITHDRAW = 'day-high-withdraw-value'
    DAY_HIGH_CRYPTO_PAIR_DEPOSIT = 'day-high-crypto-pair-deposit'
    MONTH_HIGH_WITHDRAW = 'month-high-withdraw-value'
    WITHDRAW_VALUE_PEAK = 'withdraw-value-peak'
    HIGH_DEPOSITS_VALUE = 'high-deposits-value'
    HIGH_TRANSFERS_COUNT = 'high-transfers-count'
    HIGH_WITHDRAW = 'high-withdraw'
    AUTO_WITHDRAW_CEIL = 'auto-withdraw-ceil'

    TYPE_SYSTEM, TYPE_FATA = 'system', 'fata'

    reason: str
    value: float
    expected: float
    whitelist: bool = False
    type: str = TYPE_SYSTEM


def get_risks_html(risks: List[RiskFactor]):
    data = []

    for risk in risks:
        risk_dict = risk.__dict__
        risk_dict['value'] = humanize_number(risk_dict['value'])
        risk_dict['expected'] = humanize_number(risk_dict['expected'])

        data.append(risk_dict)

    return get_table_html(RiskFactor.__dict__['__annotations__'].keys(), data)


def get_common_system_risks(account: Account) -> list:
    risks = []
    config = SystemConfig.get_system_config()

    transfers = Transfer.objects.filter(
        wallet__account=account,
    ).exclude(
        status=CANCELED
    )

    deposits = transfers.filter(
        deposit=True,
        created__gte=timezone.now() - timedelta(days=1)
    ).values('network', 'wallet__asset').annotate(value=Sum('usdt_value'))

    for deposit in deposits:
        network_asset = NetworkAsset.objects.get(network_id=deposit['network'], asset_id=deposit['wallet__asset'])

        max_allowed = network_asset.max_allowed_daily_deposit_value

        if max_allowed is None:
            max_allowed = config.default_max_allowed_coin_network_daily_deposit_value

        if deposit['value'] > max_allowed:
            risks.append(
                RiskFactor(
                    reason=RiskFactor.DAY_HIGH_CRYPTO_PAIR_DEPOSIT,
                    value=float(deposit['value']),
                    expected=max_allowed
                )
            )

    return risks


def get_withdraw_fata_risks(transfer: Transfer) -> list:
    risks = []
    account = transfer.wallet.account

    last_48h_fiat_deposit = Payment.objects.filter(
        user=account.user,
        created__gte=timezone.now() - timedelta(days=2)
    ).aggregate(val=Sum('amount'))['val'] or 0

    potential_debt = account.get_total_balance_irt(side=BUY) - transfer.irt_value - last_48h_fiat_deposit
    account_safety_multiplier = account.user.withdraw_risk_level_multiplier
    safe_debt_irt_val = FATA_SAFE_DEBT_IRT_VALUE * account_safety_multiplier

    if potential_debt >= safe_debt_irt_val:
        return [
            RiskFactor(
                reason=RiskFactor.FIAT_DEBT_RISK,
                value=round(potential_debt),
                expected=round(safe_debt_irt_val),
                whitelist=True,
                type=RiskFactor.TYPE_FATA,
            )
        ]

    risky_debt_irt_value = FATA_RISKY_DEBT_IRT_VALUE * account_safety_multiplier

    if potential_debt <= risky_debt_irt_value:
        risks.append(
            RiskFactor(
                reason=RiskFactor.FIAT_DEBT_RISK,
                value=round(potential_debt),
                expected=round(risky_debt_irt_value),
                type=RiskFactor.TYPE_FATA,
            )
        )

    devices = LoginActivity.objects.filter(user=account.user).values('device').distinct().count()
    if devices > 1:
        risks.append(
            RiskFactor(
                reason=RiskFactor.MULTIPLE_DEVICES,
                value=devices,
                expected=1,
                type=RiskFactor.TYPE_FATA,
            )
        )

    withdraws = Transfer.objects.filter(
        wallet__account=account,
        deposit=False,
    ).exclude(
        status=CANCELED
    )

    if not withdraws.exclude(id=transfer.id).filter(out_address=transfer.out_address):
        risks.append(
            RiskFactor(
                reason=RiskFactor.NEW_RECIPIENT_ADDRESS,
                value=1,
                expected=2,
                type=RiskFactor.TYPE_FATA,
            )
        )

    return risks


def get_withdraw_system_risks(transfer: Transfer) -> list:
    risks = []
    account = transfer.wallet.account

    transfers = Transfer.objects.filter(
        wallet__account=account,
    ).exclude(
        status=CANCELED
    )

    withdraws = transfers.filter(deposit=False)

    current_day_withdraw_value = withdraws.filter(
        created__gte=timezone.now() - timedelta(days=1)
    ).aggregate(value=Sum('usdt_value'))['value'] or 0

    if current_day_withdraw_value > SAFE_DAILY_WITHDRAW_VALUE:
        risks.append(
            RiskFactor(
                reason=RiskFactor.DAY_HIGH_WITHDRAW,
                value=float(current_day_withdraw_value),
                expected=float(SAFE_DAILY_WITHDRAW_VALUE),
            )
        )

    last_30_days_withdraw_value = withdraws.filter(
        created__gte=timezone.now() - timedelta(days=30)
    ).aggregate(value=Sum('usdt_value'))['value'] or 0

    if last_30_days_withdraw_value > SAFE_MONTHLY_WITHDRAW_VALUE:
        risks.append(
            RiskFactor(
                reason=RiskFactor.MONTH_HIGH_WITHDRAW,
                value=float(last_30_days_withdraw_value),
                expected=float(SAFE_MONTHLY_WITHDRAW_VALUE),
            )
        )

    current_withdraws = withdraws.filter(
        created__range=(timezone.now() - timedelta(days=31), timezone.now() - timedelta(days=1))
    )

    if current_withdraws.count() > 2:
        max_withdraw_value = current_withdraws.aggregate(value=Max('usdt_value'))['value'] or 0
        expected_withdraw_value = max_withdraw_value * 4

        if transfer.usdt_value > max(expected_withdraw_value, 1000):
            risks.append(
                RiskFactor(
                    reason=RiskFactor.WITHDRAW_VALUE_PEAK,
                    value=float(current_day_withdraw_value),
                    expected=float(expected_withdraw_value)
                )
            )

    deposits_value = transfers.filter(
        deposit=True,
        created__gte=timezone.now() - timedelta(days=3)
    ).aggregate(value=Sum('usdt_value'))['value'] or 0

    if deposits_value > SAFE_CURRENT_DEPOSITS_VALUE:
        risks.append(
            RiskFactor(
                reason=RiskFactor.HIGH_DEPOSITS_VALUE,
                value=float(deposits_value),
                expected=SAFE_CURRENT_DEPOSITS_VALUE
            )
        )

    transfer_counts = transfers.filter(
        created__gte=timezone.now() - timedelta(days=3)
    ).count()

    if current_day_withdraw_value > 50 and transfer_counts > SAFE_CURRENT_TRANSFERS_COUNT:
        risks.append(
            RiskFactor(
                reason=RiskFactor.HIGH_TRANSFERS_COUNT,
                value=transfer_counts,
                expected=SAFE_CURRENT_TRANSFERS_COUNT
            )
        )

    return risks


def can_withdraw(account: Account, request, value_usdt: Decimal) -> bool:  # todo :: check margin positive equity
    withdraw_conditions = check_withdraw_conditions(account, value_usdt)

    if not withdraw_conditions:
        hijacker_id = get_hijacker_id(request)

        if not hijacker_id:
            return False

        hijacker = User.objects.get(id=hijacker_id)

        if hijacker.is_superuser:
            return True

    return withdraw_conditions


def check_withdraw_conditions(account: Account, value_usdt: Decimal) -> bool:
    if not settings.WITHDRAW_ENABLE or not account.user.can_withdraw:
        return False

    if Wallet.objects.filter(account=account, market=Wallet.DEBT, balance__lt=0):
        return False

    if Wallet.objects.filter(account=account, market=Wallet.SPOT, balance__lt=0):
        if account.get_total_balance_usdt() < value_usdt:
            return False

    return True
