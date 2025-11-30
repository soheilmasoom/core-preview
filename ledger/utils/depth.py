from decimal import Decimal
from typing import List, Tuple


class NoDepthError(Exception):
    pass


THRESHOLD_SPREADS = [
    Decimal('0'), Decimal('0.001'), Decimal('0.002'), Decimal('0.003'), Decimal('0.005'), Decimal('0.0075'),
    Decimal('0.01'), Decimal('0.015'), Decimal('0.02'), Decimal('0.025'), Decimal('0.03'), Decimal('0.04'),
    Decimal('0.05')
]

BID = 0
ASK = 1


def parse_depth(depth: List[tuple], max_spread: Decimal = Decimal('0.05')):
    if len(depth) < 1:
        return

    depth_cum = []
    cum_value = 0
    initial_price = Decimal(depth[0][0])

    for price, amount in depth:
        price, amount = Decimal(price), Decimal(amount)
        cum_value += price * amount
        spread = abs(price / initial_price - 1)

        if spread > max_spread:
            break

        depth_cum.append((spread, int(cum_value)))

    return depth_cum


def encode_depth(depth: List[tuple]):
    """
    price-spreads volumes seperated by dash
    """
    depth_cum = parse_depth(depth)
    price = depth[0][0]

    side = BID

    if len(depth) > 1 and Decimal(depth[1][0]) > Decimal(depth[0][0]):
        side = ASK

    volumes = []

    last_cum_value = 0
    threshold_spread = THRESHOLD_SPREADS[0]

    for spread, cum_value in depth_cum:
        while spread > threshold_spread:
            volumes.append(last_cum_value)

            if len(volumes) >= len(THRESHOLD_SPREADS):
                break

            threshold_spread = THRESHOLD_SPREADS[len(volumes)]

        last_cum_value = cum_value

    while len(volumes) < len(THRESHOLD_SPREADS):
        volumes.append(last_cum_value)

    return '-'.join(map(str, [price, side, *volumes]))


def decode_depth(encoded: str) -> Tuple[Decimal, int, List[int]]:
    parts = encoded.split('-')
    return Decimal(parts[0]), int(parts[1]), list(map(int, parts[2:]))


def get_base_price_and_spread(encoded: str, amount: Decimal) -> Tuple[Decimal, Decimal]:
    base_price, side, values = decode_depth(encoded)
    assert len(values) == len(THRESHOLD_SPREADS)

    value = amount * base_price

    for i in range(len(values)):
        if value <= values[i]:
            break
    else:
        raise NoDepthError(values[-1] / base_price)

    spread = THRESHOLD_SPREADS[i]

    if side == BID:
        spread = -spread

    return base_price, spread
