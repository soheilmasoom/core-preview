from django.db import models
from django.db.models import Manager, Count, Case, When, Value, Q, F, BooleanField
from multimedia.storage import PublicMediaStorage


class HighlightManager(Manager):
    def get_user_highlights(self, user):
        return self.filter(is_active=True).annotate(
            total_stories=Count('stories'),
            seen_stories=Count('stories__views', filter=Q(stories__views__user=user))
        ).annotate(
            seen=Case(
                When(
                    Q(total_stories__gt=0) & Q(total_stories=F('seen_stories')),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        )


class Highlight(models.Model):
    title = models.CharField(max_length=255)
    image = models.ImageField(storage=PublicMediaStorage(), upload_to='highlights/')
    is_active = models.BooleanField(default=True)

    objects = HighlightManager()

    def __str__(self):
        return self.title


class Story(models.Model):
    highlight = models.ForeignKey(
        Highlight,
        on_delete=models.CASCADE,
        related_name='stories'
    )
    media = models.FileField(storage=PublicMediaStorage(), upload_to='stories/')
    text = models.TextField(blank=True, null=True)
    order = models.IntegerField(default=0, help_text="Determines the order of this story within the highlight.")

    def __str__(self):
        return f"Story for {self.highlight.title} (Order: {self.order})"

    class Meta:
        ordering = ['order']


class StoryView(models.Model):
    user = models.ForeignKey(to='accounts.User', on_delete=models.CASCADE)
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='views')
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'story')
        indexes = [
            models.Index(fields=['user', 'story']),
        ]

    def __str__(self):
        return f"{self.user} viewed {self.story}"
