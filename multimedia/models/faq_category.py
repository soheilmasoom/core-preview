from django.db import models


class FAQCategory(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=256, unique=True, db_index=True)

    def __str__(self):
        return self.slug


class FAQ(models.Model):
    category = models.ForeignKey(FAQCategory, related_name='faqs', on_delete=models.CASCADE)
    question_text = models.CharField(max_length=255)
    answer_text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question_text
