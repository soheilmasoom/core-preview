from django.db import models
from django.db.models import UniqueConstraint, Q


class AddressKey(models.Model):
    account = models.ForeignKey('accounts.account', on_delete=models.PROTECT)
    address = models.CharField(max_length=256)  # pointer_address
    public_address = models.CharField(max_length=256)
    architecture = models.CharField(max_length=16)
    created = models.DateTimeField(auto_now_add=True)
    memo = models.CharField(max_length=256, blank=True, db_index=True)

    deleted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('account', 'address', 'memo')

        constraints = [
            UniqueConstraint(
                fields=['account', 'architecture'],
                name="ledger_addresskey_unique_account_architecture",
                condition=Q(deleted=False),
            ),
            UniqueConstraint(
                fields=['memo', 'architecture'],
                name="ledger_addresskey_unique_memo_architecture",
                condition=~Q(memo=''),
            ),
        ]

    def __str__(self):
        return self.address
