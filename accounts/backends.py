from django.contrib.auth.backends import ModelBackend
from rest_framework.exceptions import PermissionDenied

from accounts.models import User


class AuthenticationBackend(ModelBackend):

    def authenticate(self, request, **credentials):
        login = credentials.get('login') or credentials.get('username') or credentials.get('phone')
        password = credentials.get('password')

        if not login or not password:
            return

        user = User.get_user_from_login(login)
        if not user:
            User().set_password(password)
            return

        if user.check_password(password):
            if self.user_can_authenticate(user):
                return user
            else:
                raise PermissionDenied({'reason': 'حساب شما تعلیق شده است.'})
