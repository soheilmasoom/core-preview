from django.conf import settings


if settings.DEBUG_OR_TESTING:
    from accounts.models import Referral, Account, VerificationCode, User, TrafficSource, CustomToken
    from accounts.utils.validation import generate_random_code

    def new_phone() -> str:
        return '09' + str(generate_random_code(9))

    def new_user(phone=None, level=User.LEVEL2) -> User:
        if not phone:
            phone = new_phone()
        user = User.objects.create(username=phone, phone=phone, level=level)
        return user


    def new_traffic_source() -> TrafficSource:
        return TrafficSource.objects.create(
            user=new_user(),
            utm_source='google',
            utm_medium='cpc'
        )


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

    def new_custom_token(user: User) -> str:
        token, _ = CustomToken.objects.get_or_create(user=user)
        return token.key

