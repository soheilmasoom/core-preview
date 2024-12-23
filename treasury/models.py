from django.db import models
from django.core.validators import MinValueValidator


class PreciousMetalChoices:
    GOLD = 'XAU'
    SILVER = 'XAG'

    CHOICES = [
        (GOLD, 'Gold'),
        (SILVER, 'Silver'),
    ]


class Treasury(models.Model):
    metal_type = models.CharField(
        max_length=10,
        choices=PreciousMetalChoices.CHOICES,
        unique=True,
        verbose_name="Metal Type"
    )
    current_balance = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Current Balance (grams)"
    )
    sold_amount = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Sold Amount (grams)"
    )
    bank_reserved = models.DecimalField(
        max_digits=20,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        verbose_name="Bank Reserved Amount (grams)"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Treasuries"

    def __str__(self):
        return f"{self.get_metal_type_display()} Treasury"
