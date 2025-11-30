import re

from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

PHONE_REGEX = r'^((09\d{9})|(00\d{8,15}))$'


class RegexValidator:
    def __init__(self, pattern: str):
        self.pattern = pattern

    def __call__(self, value):
        if not re.match(self.pattern, value):
            raise ValidationError('یک مقدار معتبر وارد کنید.')


def mobile_number_validator(value):
    if not re.match(PHONE_REGEX, value):
        raise ValidationError('شماره موبایل معتبر نیست.')


def telephone_number_validator(value):
    if not re.match(r'^0?[1-8]\d{9}$', value):
        raise ValidationError('شماره تلفن معتبر نیست.')


def email_validator(value):
    if not re.match(r'^\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b$', value):
        raise ValidationError('ایمیل معتبر نیست.')


def iran_mobile_number_validator(value):
    if not re.match(r'^(09)(\d){9}$', value):
        raise ValidationError('شماره موبایل برای ایران معتبر نیست.')


def national_card_code_validator(value):

    if type(value) is str and 8 <= len(value) < 10:
        value = (10 - len(value)) * '0' + value

    if not re.match(r'^[0-9]{10}$', value):
        raise ValidationError('کد ملی باید 10 رقمی باشد.')

    array = list(map(int, value))

    _sum = 0
    for i in range(9):
        _sum += (10 - i) * array[i]

    control = _sum % 11

    if control >= 2:
        control = 11 - control

    if control != array[9]:
        raise ValidationError('کد ملی معتبر نیست.')


def password_validator(password: str, user=None):
    errors = []
    try:
        validate_password(password=password, user=user)
    except ValidationError as e:
        errors.extend(e.messages)

    if errors:
        raise ValidationError(errors)


def is_phone(phone: str) -> bool:
    return bool(re.match(PHONE_REGEX, phone))


def company_national_id_validator(value):
    if not re.match(r'^\d{11}$', value):
        raise ValidationError('شناسه ملی شرکت به درستی وارد نشده‌است.')

    array = list(map(int, value))

    _sum = 0
    const = array[9] + 2
    coefficients = [29, 27, 23, 19, 17]
    for i in range(10):
        _sum += (const + array[i]) * coefficients[i % 5]

    control = (_sum % 11) % 10
    if control != array[10]:
        raise ValidationError('شناسه‌ملی  معتبر نیست.')
