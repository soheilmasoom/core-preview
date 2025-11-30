import re

from django.core.exceptions import ValidationError


def iban_validator(iban: str):
    if not re.match(r'^IR[0-9]{24}$', iban):
        raise ValidationError('شماره شبا نامعتبر است.')

    value = iban[4:] + iban[:4]
    value = value.replace('I', '18').replace('R', '27')

    if int(value) % 97 != 1:
        raise ValidationError('شماره شبا نامعتبر است.')

    bank_code = iban[4:8]

    if bank_code in ('0630', '0520', '0650', '0790', '0730'):
        raise ValidationError('شماره شبا مربوط به بانک‌های ادغام شده است. لطفا شماره شبای دیگری وارد کنید.')


def bank_card_pan_validator(value: str):
    if not re.match(r'^[0-9]{16}$', value):
        raise ValidationError('شماره کارت نامعتبر است.')

    _sum = 0

    array = list(map(int, value))

    for index, digit in enumerate(array):
        s = (2 - (index % 2)) * digit
        if s > 9:
            s -= 9
        _sum += s

    if _sum % 10 != 0:
        raise ValidationError('شماره کارت نامعتبر است.')
