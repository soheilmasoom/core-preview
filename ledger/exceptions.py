from rest_framework.exceptions import ValidationError

from _base import settings
from ledger.utils.external_price import BUY


class InsufficientBalance(Exception):
    pass


class InsufficientDebt(Exception):
    pass


class MaxBorrowableExceeds(Exception):
    pass


class HedgeError(Exception):
    pass


class SmallAmountTrade(Exception):
    pass


class LargeAmountTrade(ValidationError):
    pass


class AbruptDecrease(Exception):
    pass


class SmallDepthError(Exception):
    pass


class NoPriceError(Exception):
    pass


class FetchError(Exception):
    pass


from rest_framework.exceptions import ValidationError


class UnableToTradeError(ValidationError):
    def __init__(self, side=None, asset=None, detail=None, code=None):
        symbol = asset.symbol
        is_crypto = settings.EXCHANGE_TYPE.is_crypto
        if not detail:
            side_verbose = 'خرید' if side == BUY else 'فروش'
            if is_crypto:
                asset_name = 'این رمزارز'
            else:
                asset_name = 'طلا' if symbol in ['XAU', 'XAUM'] else 'نقره' if symbol == 'XAG' else 'این دارایی'

            detail = f'امکان {side_verbose} {asset_name} وجود ندارد.'

        super().__init__(detail=detail, code=code)


class UnableToTradeRightNowError(ValidationError):
    def __init__(self, side=None, asset=None, detail=None, code=None):
        symbol = asset.symbol
        is_crypto = settings.EXCHANGE_TYPE.is_crypto
        if not detail:
            side_verbose = 'خرید' if side == BUY else 'فروش'
            if is_crypto:
                asset_name = 'این رمزارز'
            else:
                asset_name = 'طلا' if symbol in ['XAU', 'XAUM'] else 'نقره' if symbol == 'XAG' else 'این دارایی'

            detail = f'در حال حاضر امکان {side_verbose} {asset_name} وجود ندارد.'

        super().__init__(detail=detail, code=code)


class ExceedsMaximumAmountError(ValidationError):
    def __init__(self, side=None, asset=None, max_amount=None, detail=None, code=None):
        symbol = asset.symbol
        is_crypto = settings.EXCHANGE_TYPE.is_crypto
        if not detail:
            side_verbose = 'خرید' if side == BUY else 'فروش'
            if is_crypto:
                asset_name = 'این رمزارز'
                quote = symbol.name
            else:
                asset_name = 'طلا' if symbol in ['XAU', 'XAUM'] else 'نقره' if symbol == 'XAG' else 'این دارایی'
                quote = 'گرم'
                if symbol == 'XAUM':
                    quote = 'میلی گرم'

            detail = 'حداکثر مقدار قابل {} {} {} {} است.'.format(side_verbose, asset_name, max_amount, quote)

        super().__init__(detail=detail, code=code)
