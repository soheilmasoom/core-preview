from django.db import models


class ColdWallet(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    architecture = models.CharField(max_length=12, db_index=True)
    address = models.CharField(max_length=256, unique=True)
    comment = models.TextField(blank=True)

    def __str__(self):
        return f'{self.address},{self.architecture}'
