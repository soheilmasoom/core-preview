from accounts.authentication import SetPasswordAccessToken
from accounts.models.user import User
from datetime import timedelta


class Widget:
    NEW_USER, VERIFIED_USER, UNVERIFIED_USER = 'n', 'v', 'u'

    @classmethod
    def get_user_verification_status(self, phone):
        user = User.objects.filter(phone=phone).first()
        if not user:
            return self.NEW_USER
        elif not user.national_code or not user.national_code_verified:
            return self.UNVERIFIED_USER
        return self.VERIFIED_USER

    @classmethod
    def generate_set_password_token(self, user):
        access_token = SetPasswordAccessToken.for_user(user)
        access_token.set_exp(lifetime=timedelta(minutes=60))
        return str(access_token)
