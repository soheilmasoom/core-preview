from django import forms
from django.contrib.postgres.fields import ArrayField


class MultiSelectArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {
            "form_class": forms.MultipleChoiceField,
            "choices": self.base_field.choices,
            "widget": forms.CheckboxSelectMultiple,
            **kwargs
        }

        return super(ArrayField, self).formfield(**defaults)
