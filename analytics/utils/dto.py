import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Union, ClassVar, Type


@dataclass
class BaseEvent:
    v: ClassVar[str] = '1'
    created: datetime
    user_id: Union[int, None, Type[int]]
    event_id: uuid
    login_activity_id: Union[int, None, Type[int]]

    def serialize(self):
        pass


@dataclass(kw_only=True)
class UserEvent(BaseEvent):
    first_name: str
    last_name: str
    referrer_id: str
    type: ClassVar[str] = 'user'
    level_2_verify_datetime: datetime
    level_3_verify_datetime: datetime
    level: int
    birth_date: datetime
    can_withdraw: bool
    can_trade: bool
    promotion: str
    chat_uuid: uuid
    verify_status: str
    reject_reason: str
    first_fiat_deposit_date: datetime
    first_crypto_deposit_date: datetime

    def serialize(self):
        return {
            'user_id': self.user_id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'first_name': self.first_name,
            'last_name': self.last_name,
            'referrer_id': self.referrer_id,
            'type': self.type,
            'level_2_verify_datetime': self.level_2_verify_datetime.isoformat() if self.level_2_verify_datetime else None,
            'level_3_verify_datetime': self.level_3_verify_datetime.isoformat() if self.level_3_verify_datetime else None,
            'level': self.level,
            'birth_date': self.birth_date.isoformat() if self.birth_date else None,
            'can_withdraw': self.can_withdraw,
            'can_trade': self.can_trade,
            'promotion': self.promotion,
            'chat_uuid': str(self.chat_uuid),
            'verify_status': self.verify_status,
            'reject_reason': self.reject_reason,
            'first_fiat_deposit_date': self.first_fiat_deposit_date.isoformat() if self.first_fiat_deposit_date else None,
            'first_crypto_deposit_date': self.first_crypto_deposit_date.isoformat()if self.first_crypto_deposit_date else None
        }


@dataclass(kw_only=True)
class TransferEvent(BaseEvent):
    id: int
    amount: Decimal
    coin: str
    network: str
    is_deposit: bool
    type: ClassVar[str] = 'transfer'
    value_irt: Decimal
    value_usdt: Decimal

    def serialize(self):
        return {
            'id': self.id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'user_id': self.user_id,
            'amount': str(self.amount),
            'coin': self.coin,
            'network': self.network,
            'type': self.type,
            'is_deposit': self.is_deposit,
            'value_irt': str(self.value_irt),
            'value_usdt': str(self.value_usdt),
        }


@dataclass(kw_only=True)
class TradeEvent(BaseEvent):
    id: int
    amount: Decimal
    symbol: str
    price: Decimal
    trade_type: str
    market: str
    value_irt: Decimal
    value_usdt: Decimal
    type: ClassVar[str] = 'trade'
    side: str

    def serialize(self):
        return {
            'id': self.id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'user_id': self.user_id,
            'amount': str(self.amount),
            'symbol': self.symbol,
            'price': str(self.price),
            'type': self.type,
            'trade_type': self.trade_type,
            'market': self.market,
            'value_irt': str(self.value_irt),
            'value_usdt': str(self.value_usdt),
            'side': self.side
        }


@dataclass(kw_only=True)
class TradeRevenueEvent(BaseEvent):
    id: int
    amount: Decimal
    symbol: str
    price: Decimal
    source: str
    market: str
    value_irt: Decimal
    value_usdt: Decimal
    type: ClassVar[str] = 'revenue'
    side: str
    fee_revenue: Decimal
    gap_revenue: Decimal

    def serialize(self):
        return {
            'id': self.id,
            'type': self.type,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'user_id': self.user_id,
            'amount': str(self.amount),
            'symbol': self.symbol,
            'price': str(self.price),
            'source': self.source,
            'market': self.market,
            'value_irt': str(self.value_irt),
            'value_usdt': str(self.value_usdt),
            'side': self.side,
            'fee_revenue': str(self.fee_revenue),
            'gap_revenue': str(self.gap_revenue or 0),
        }


@dataclass(kw_only=True)
class LoginEvent(BaseEvent):
    id: int
    device: str
    type: ClassVar[str] = 'login'
    is_signup: bool
    user_agent: str
    device_type: str
    location: str
    os: str
    browser: str
    city: str
    country: str
    native_app: bool

    def serialize(self):
        return {
            'user_id': self.user_id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'device': self.device,
            'type': self.type,
            'is_signup': self.is_signup,
            'user_agent': self.user_agent,
            'device_type': self.device_type,
            'location': self.location,
            'os': self.os,
            'browser': self.browser,
            'city': self.city,
            'country': self.country,
            'native_app': self.native_app,
            'id': self.id

        }


@dataclass(kw_only=True)
class TrafficSourceEvent(BaseEvent):
    type: ClassVar[str] = 'traffic_source'
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_content: str
    utm_term: str

    def serialize(self):
        return {
            'user_id': self.user_id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'type': self.type,
            'utm_source': self.utm_source,
            'utm_medium': self.utm_medium,
            'utm_campaign': self.utm_campaign,
            'utm_content': self.utm_content,
            'utm_term': self.utm_term,
        }


@dataclass(kw_only=True)
class StakeRequestEvent(BaseEvent):
    type: ClassVar[str] = 'staking'
    stake_request_id: int
    stake_option_id: int
    amount: Decimal
    status: str
    coin: str
    apr: Decimal

    def serialize(self):
        return {
            'user_id': self.user_id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'type': self.type,
            'stake_request_id': self.stake_request_id,
            'stake_option_id': self.stake_option_id,
            'amount': str(self.amount),
            'status': self.status,
            'coin': self.coin,
            'apr': str(self.apr)
        }


@dataclass(kw_only=True)
class PrizeEvent(BaseEvent):
    type: ClassVar[str] = 'prize'
    id: int
    amount: Decimal
    coin: str
    voucher_expiration: datetime
    value: Decimal
    achievement_type: str

    def serialize(self):
        return {
            'user_id': self.user_id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'type': self.type,
            'id': self.id,
            'amount': str(self.amount),
            'coin': self.coin,
            'voucher_expiration': self.voucher_expiration.isoformat() if self.voucher_expiration else None,
            'value': str(self.value),
            'achievement_type': self.achievement_type
        }


@dataclass(kw_only=True)
class WalletEvent(BaseEvent):
    type: ClassVar[str] = 'wallet'
    id: int
    coin: str
    market: str
    balance: Decimal

    def serialize(self):
        return {
            'user_id': self.user_id,
            'login_activity_id': self.login_activity_id,
            'created': self.created.isoformat(),
            'v': self.v,
            'event_id': str(self.event_id),
            'type': self.type,
            'id': self.id,
            'coin': self.coin,
            'market': self.market,
            'balance': str(self.balance),
        }


@dataclass(kw_only=True)
class TransactionEvent(BaseEvent):
    type: ClassVar[str] = 'transaction'
    id: int
    sender_wallet_id: int
    receiver_wallet_id: int
    amount: Decimal
    group_id: uuid
    scope: str

    def serialize(self):
        return {
            'created': self.created.isoformat(),
            'login_activity_id': self.login_activity_id,
            'v': self.v,
            'event_id': str(self.event_id),
            'type': self.type,
            'id': self.id,
            'amount': str(self.amount),
            'sender_wallet_id': self.sender_wallet_id,
            'receiver_wallet_id': self.receiver_wallet_id,
            'group_id': str(self.group_id),
            'scope': self.scope
        }
