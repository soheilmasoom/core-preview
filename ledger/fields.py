from django.db import models


class WithdrawSources:
    SELF, INTERNAL, INTERNAL_ACCOUNT, PROVIDER, MANUAL = 'self', 'internal', 'internal_account', 'provider', 'manual'
    CHOICES = (SELF, SELF), (INTERNAL, INTERNAL), (INTERNAL_ACCOUNT, INTERNAL_ACCOUNT), (PROVIDER, PROVIDER), (MANUAL, MANUAL)

    @classmethod
    def get_db_field(cls):
        return models.CharField(
            max_length=16,
            default=cls.SELF,
            choices=cls.CHOICES
        )
