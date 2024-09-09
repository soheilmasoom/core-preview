from django.db import models


class SearchHistory(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey('accounts.Account', on_delete=models.CASCADE)
    query = models.TextField()
    result = models.TextField(blank=True)
