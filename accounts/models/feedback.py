from django.core.validators import MaxValueValidator
from django.db import models

from ledger.utils.fields import get_created_field


# class Feedback(models.Model):
#     NPS = 'nps'
#     TYPE_CHOICES = (NPS, NPS),
#
#     created = get_created_field()
#     name = models.CharField(max_length=64, unique=True)
#     type = models.CharField(max_length=8, choices=TYPE_CHOICES)
#
#     def __str__(self):
#         return self.name


class UserFeedback(models.Model):
    created = get_created_field()
    # feedback = models.ForeignKey('Feedback', on_delete=models.CASCADE)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, unique=True)

    score = models.PositiveIntegerField(validators=[MaxValueValidator(10)])
    comment = models.TextField(max_length=4096, blank=True)

    # class Meta:
    #     unique_together = ('user', 'feedback')
