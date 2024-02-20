from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from accounts.models import SystemConfig
from ledger.utils.fields import DONE


def _ban_transfer(crypto: bool, deposit: bool) -> bool:
    config = SystemConfig.get_system_config()

    if deposit:
        return config.deposit_status == config.BAN or \
               (crypto and config.deposit_status == config.BAN_CRYPTO) or \
               (not crypto and config.deposit_status == config.BAN_FIAT)
    else:
        return config.withdraw_status == config.BAN or \
               (crypto and config.withdraw_status == config.BAN_CRYPTO) or \
               (not crypto and config.withdraw_status == config.BAN_FIAT)


def verify_crypto_withdraw(transfer=None) -> bool:
    if _ban_transfer(crypto=True, deposit=False):
        return False

    return True


def verify_crypto_deposit(transfer=None) -> bool:
    if _ban_transfer(crypto=True, deposit=True):
        return False

    return True


def verify_fiat_withdraw(transfer=None) -> bool:
    if _ban_transfer(crypto=False, deposit=False):
        return False

    return True


def verify_fiat_deposit(payment) -> bool:
    if _ban_transfer(crypto=False, deposit=True):
        return False

    from financial.models import Payment

    payments_sum = Payment.objects.filter(
        created__gte=timezone.now() - timedelta(days=1),
        user=payment.user,
        status=DONE
    ).aggregate(sum=Sum('amount'))['sum'] or 0

    if payments_sum > SystemConfig.get_system_config().fiat_daily_auto_verify_limit:
        return False

    return True
