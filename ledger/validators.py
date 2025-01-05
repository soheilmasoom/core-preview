from django.core.validators import RegexValidator

no_whitespace = RegexValidator(r'^\S+$', message='No whitespace allowed')