import math
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from math import ceil

from ledger.utils.cache import cache_for

AMOUNT_PRECISION = 8


def round_up_to_exponent(amount: Decimal, precision: int = 0):
    if precision < 0:
        power = Decimal(f'1e{-precision}')
        return ceil(amount / power) * power
    return ceil_precision(amount, precision)


def round_down_to_exponent(amount: Decimal, precision: int = 0):
    if precision < 0:
        power = Decimal(f'1e{-precision}')
        return amount // power * power
    return floor_precision(amount, precision)


def ceil_precision(amount: Decimal, precision: int = 0):
    step = precision_to_step(precision)
    return amount.quantize(step, rounding=ROUND_UP)


def floor_precision(amount: Decimal, precision: int = 0) -> Decimal:
    step = precision_to_step(precision)
    return amount.quantize(step, rounding=ROUND_DOWN)


def get_precision(amount: Decimal) -> int:

    if isinstance(amount, Decimal):
        amount = '{:,f}'.format(amount)

    if '.' in amount:
        amount = amount.rstrip('0').rstrip('.')

    if '.' not in amount:
        return len(amount.rstrip('0')) - len(amount)
    else:
        return len(amount.split('.')[1])


def decimal_to_str(amount: Decimal, truncate: bool = True) -> str:
    amount = '{:f}'.format(amount)
    if truncate and '.' in amount:
        amount = amount.rstrip('0').rstrip('.')
    return amount


def precision_to_step(precision: int) -> Decimal:
    precision = int(precision)

    if precision <= 0:
        return Decimal('1' + '0' * -precision)
    else:
        return Decimal('0.' + '0' * (precision - 1) + '1')


def get_presentation_amount(amount: Decimal, precision: int = None, trunc_zero: bool = True) -> str:
    if amount is None:
        return

    if not isinstance(amount, Decimal):
        amount = Decimal(amount)

    if precision is not None:
        amount = floor_precision(amount, precision)

    rounded = format(amount, 'f')

    if not trunc_zero or '.' not in rounded:
        return rounded
    else:
        return rounded.rstrip('0').rstrip('.') or '0'


def humanize_number(num):
    num = get_presentation_amount(num, precision=8)
    return '{:,f}'.format(Decimal(num))


def normalize_fraction(d: Decimal):
    normalized = d.normalize()
    sign, digit, exponent = normalized.as_tuple()
    return normalized if exponent <= 0 else normalized.quantize(1)


def is_zero_by_precision(amount: Decimal, precision: int = AMOUNT_PRECISION):
    return int(amount * 10 ** precision) == 0


@cache_for(60)
def get_symbols_tick_size() -> dict:
    from market.models import PairSymbol
    return dict(PairSymbol.objects.values_list('name', 'tick_size'))


@cache_for(60)
def get_symbols_step_size() -> dict:
    from market.models import PairSymbol
    return dict(PairSymbol.objects.values_list('name', 'step_size'))


def get_symbol_presentation_price(symbol: str, amount: Decimal, trunc_zero: bool = False):
    if symbol == 'IRTUSDT':
        precision = 8
    else:
        precision = get_symbols_tick_size().get(symbol, 0)

    return get_presentation_amount(amount, precision, trunc_zero=trunc_zero)


def get_symbol_presentation_amount(symbol: str, amount: Decimal):
    precision = get_symbols_step_size().get(symbol, 0)
    return get_presentation_amount(amount, precision, trunc_zero=True)


def get_coin_presentation_balance(coin: str, balance: Decimal):
    if coin == 'IRT':
        precision = 0
    else:
        precision = None

    return get_presentation_amount(balance, precision=precision)


def get_margin_coin_presentation_balance(coin: str, balance: Decimal):
    if coin == 'IRT':
        precision = 0
    elif coin == 'USDT':
        precision = 2
    else:
        precision = None

    return get_presentation_amount(balance, precision=precision)


def log10_round(num: Decimal, floor: bool = True):
    if floor:
        func = math.floor
    else:
        func = math.ceil

    return Decimal(10) ** func(math.log10(num))
