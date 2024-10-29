from django.db import models


class FAQCategory(models.Model):
    LINK = 'link'
    QA = 'qa'
    FAQ_TYPES = [
        (LINK, 'Link'),
        (QA, 'QA'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=256, unique=True, db_index=True)
    type = models.CharField(max_length=4, choices=FAQ_TYPES, default=QA)

    def __str__(self):
        return self.slug


class FAQ(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    category = models.ForeignKey(FAQCategory, related_name='faqs', on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True)
    answer = models.TextField(blank=True)
    link = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.title
