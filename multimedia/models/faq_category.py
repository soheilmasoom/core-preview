from django.db import models


class FAQCategory(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=256, unique=True, db_index=True)

    def __str__(self):
        return self.slug


class FAQ(models.Model):
    LINK = 'link'
    QA = 'qa'
    FAQ_TYPES = [
        (LINK, LINK),
        (QA, QA),
    ]

    category = models.ForeignKey(FAQCategory, related_name='faqs', on_delete=models.CASCADE)
    question_text = models.CharField(max_length=255)
    answer_text = models.TextField()
    type = models.CharField(max_length=4, choices=FAQ_TYPES, default='qa')
    title = models.CharField(max_length=255, blank=True, null=True)
    link = models.URLField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question_text
