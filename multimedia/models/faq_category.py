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
    question_text = models.CharField(max_length=255, null=True, blank=True)
    answer_text = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=4, choices=FAQ_TYPES)
    title = models.CharField(max_length=255, blank=True, null=True)
    link = models.URLField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)

def __str__(self):
    if self.type == self.LINK:
        return self.title or ""
    return self.question_text or ""

