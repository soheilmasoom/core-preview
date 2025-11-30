from dataclasses import dataclass
from decimal import Decimal

from pydantic.decorator import validate_arguments


@validate_arguments
@dataclass
class MarketInfo:
    id: int
    coin: str
    base_coin: str
    exchange: str

    type: str  # spot | futures

    tick_size: Decimal
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal

    min_notional: Decimal


@validate_arguments
@dataclass
class NetworkInfo:
    coin: str
    network: str

    withdraw_min: Decimal
    withdraw_max: Decimal
    withdraw_fee: Decimal
    withdraw_enable: bool
    deposit_enable: bool
    address_regex: str


@validate_arguments
@dataclass
class WithdrawStatus:
    status: str
    tx_id: str


@validate_arguments
@dataclass
class CoinInfo:
    coin: str = ''
    price: float = 0
    change_24h: float = 0
    volume_24h: float = 0
    change_7d: float = 0
    high_24h: float = 0
    low_24h: float = 0
    change_1h: float = 0
    cmc_rank: int = 0
    market_cap: float = 0
    circulating_supply: float = 0
    weekly_trend_url: str = ''

