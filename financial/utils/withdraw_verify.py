import dataclasses
from decimal import Decimal

from django.db.models import Sum

from financial.models import FiatWithdrawRequest, Payment, Gateway
from ledger.utils.fields import CANCELED
from ledger.utils.withdraw_verify import RiskFactor


def auto_verify_fiat_withdraw(withdraw: FiatWithdrawRequest):
    risks = get_fiat_withdraw_risks(withdraw)

    if risks:
        withdraw.risks = list(map(dataclasses.asdict, risks))
        withdraw.save(update_fields=['risks'])

    return not bool(risks)


def get_fiat_withdraw_risks(withdraw: FiatWithdrawRequest) -> list:
    user = withdraw.bank_account.user
    risks = []

    total_deposits = Payment.objects.filter(
        user=user
    ).exclude(status=CANCELED).aggregate(
        amount=Sum('amount')
    )['amount'] or 0

    total_withdraws = FiatWithdrawRequest.objects.filter(
        bank_account__user=user
    ).exclude(status=CANCELED).aggregate(amount=Sum('amount'))['amount'] or 0

    expected = Decimal('1.2') * total_deposits

    if total_withdraws > expected:
        risks.append(
            RiskFactor(
                reason=RiskFactor.HIGH_WITHDRAW,
                value=float(total_withdraws),
                expected=float(expected),
            )
        )

    gateway = Gateway.get_active_withdraw()
    if gateway.max_auto_withdraw_amount is not None and withdraw.amount > gateway.max_auto_withdraw_amount:
        risks.append(
            RiskFactor(
                reason=RiskFactor.AUTO_WITHDRAW_CEIL,
                value=withdraw.amount,
                expected=gateway.max_auto_withdraw_amount,
            )
        )

    return risks
