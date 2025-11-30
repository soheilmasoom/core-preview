
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


class LargeAmountTrade(Exception):
    pass


class AbruptDecrease(Exception):
    pass


class SmallDepthError(Exception):
    pass


class NoPriceError(Exception):
    pass


class FetchError(Exception):
    pass
