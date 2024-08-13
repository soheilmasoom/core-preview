from django.db import models


class WithdrawSources:
    SELF, INTERNAL, PROVIDER, MANUAL = 'self', 'internal', 'provider', 'manual'
    CHOICES = (SELF, SELF), (INTERNAL, INTERNAL), (PROVIDER, PROVIDER), (MANUAL, MANUAL)

    @classmethod
    def get_db_field(cls):
        return models.CharField(
            max_length=8,
            default=cls.SELF,
            choices=cls.CHOICES
        )
