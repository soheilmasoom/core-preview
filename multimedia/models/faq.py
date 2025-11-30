import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django_quill.fields import QuillField
from simple_history.models import HistoricalRecords

from multimedia.utils.custom_tags import post_render_html, get_text_of_html


class BaseItem(models.Model):
    title = models.TextField(max_length=256)
    title_en = models.TextField(max_length=256)
    slug = models.SlugField(max_length=1024, unique=True, db_index=True, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        abstract = True


class Section(BaseItem):
    history = HistoricalRecords()

    ICONS = 'getting-started', 'signup', 'accounts', 'transfer', 'trade', 'earn'

    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    icon = models.CharField(max_length=256, blank=True, choices=[(i, i) for i in ICONS])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title_en)

        super().save(*args, **kwargs)

    def clean(self):
        if self.parent and self.parent == self:
            raise ValidationError('Circular dependency')

    class Meta:
        verbose_name = 'بخش'
        verbose_name_plural = 'بخش‌‌ها'
        ordering = ('order', 'id')


class Article(BaseItem):
    history = HistoricalRecords()

    parent = models.ForeignKey(Section, on_delete=models.CASCADE)
    is_pinned = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    content = QuillField(blank=True)
    _content_html = models.TextField(blank=True)
    _content_text = models.TextField(blank=True)

    def refresh(self):
        html = self.content.html
        self._content_html = post_render_html(html)
        self._content_text = get_text_of_html(self._content_html)
        self.save(update_fields=['_content_html', '_content_text'])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title_en + '-' + uuid.uuid4().hex)

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'مقاله'
        verbose_name_plural = 'مقاله‌ها'
        ordering = ('parent', 'order', 'id')
