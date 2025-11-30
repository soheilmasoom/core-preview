from accounts.models import Referral, Account
from accounts.models import VerificationCode


def create_referral(account: Account):
    referral = Referral.objects.create(
        owner=account,
        code='12345678',
        owner_share_percent=20,
    )
    return referral


def set_referred_by(account: Account, referral: Referral):
    account.referred_by = referral
    account.save()


def generate_otp_code(scope, phone, user) -> VerificationCode:
    otp_code = VerificationCode.objects.create(
        phone=phone,
        scope=scope,
        code='1',
        user=user
        )
    return otp_code.code
