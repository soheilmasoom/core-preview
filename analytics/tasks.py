import uuid
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounting.models import TradeRevenue
from accounts.models import User, LoginActivity, TrafficSource, Account
from analytics.event.producer import get_kafka_producer
from analytics.models import ActiveTrader, EventTracker
from analytics.utils.dto import LoginEvent, TransferEvent, TrafficSourceEvent, StakeRequestEvent, PrizeEvent, \
    TradeEvent, UserEvent, WalletEvent, TransactionEvent
from financial.models import FiatWithdrawRequest, Payment
from ledger.models import Transfer, Prize, OTCTrade, FastBuyToken, Wallet, Trx
from ledger.utils.fields import DONE
from ledger.utils.price import get_last_price, USDT_IRT
from market.models import Trade
from stake.models import StakeRequest


@shared_task(queue='history')
def create_analytics(now=None):
    if not now:
        now = timezone.now()

    for period in ActiveTrader.PERIODS:
        start = now - timedelta(days=period)

        accounts = set(TradeRevenue.objects.filter(
            created__range=(start, now)
        ).values_list('account', flat=True).distinct())

        old_accounts = set(TradeRevenue.objects.filter(
            created__range=(start - timedelta(days=1), now - timedelta(days=1))
        ).values_list('account', flat=True).distinct())

        ActiveTrader.objects.get_or_create(
            created=now,
            period=period,
            defaults={
                'active': len(accounts),
                'churn': len(old_accounts - accounts),
                'new': len(accounts - old_accounts),
            }
        )


@shared_task(queue='history')
def trigger_kafka_event():
    trigger_users_event()

    trigger_transfer_event()

    trigger_fiat_transfer_event()

    trigger_payment_event()

    trigger_trade_event()

    trigger_otc_trade()

    trigger_login_event()

    trigger_prize_event()

    trigger_stake_event()

    trigger_traffic_source()

    trigger_wallet_event()

    trigger_transaction_event()


def trigger_users_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.USER)
    user_list = User.objects.filter(
        id__gt=tracker.last_id
    ).order_by('id')[:threshold]

    for user in user_list:
        if not hasattr(user, 'account'):
            account = user.get_account()
        else:
            account = user.account
        referrer_id = account and account.referred_by and account.referred_by.owner.user_id
        event = UserEvent(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            referrer_id=referrer_id,
            created=user.date_joined,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(user.id) + UserEvent.type),
            level_2_verify_datetime=user.level_2_verify_datetime,
            level_3_verify_datetime=user.level_3_verify_datetime,
            level=user.level,
            birth_date=user.birth_date,
            can_withdraw=user.can_withdraw,
            can_trade=user.can_trade,
            promotion=user.promotion,
            chat_uuid=user.chat_uuid,
            verify_status=user.verify_status,
            reject_reason=user.reject_reason,
            first_fiat_deposit_date=user.first_fiat_deposit_date,
            first_crypto_deposit_date=user.first_crypto_deposit_date,
        )
        get_kafka_producer().produce(event, instance=user)


def trigger_transfer_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.TRANSFER)
    transfer_list = Transfer.objects.filter(
        id__gt=tracker.last_id, status=DONE
    ).order_by('id')[:threshold]

    for transfer in transfer_list:
        event = TransferEvent(
            id=transfer.id,
            user_id=transfer.wallet.account.user_id,
            amount=transfer.amount,
            coin=transfer.wallet.asset.symbol,
            network=transfer.network.symbol,
            created=transfer.created,
            is_deposit=transfer.deposit,
            value_irt=transfer.irt_value,
            value_usdt=transfer.usdt_value,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(transfer.id) + TransferEvent.type + 'crypto'),
            login_activity_id=transfer.login_activity_id or ''
        )

        get_kafka_producer().produce(event, instance=transfer)


def trigger_fiat_transfer_event(threshold=1000):
    usdt_price = get_last_price(USDT_IRT)
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.FIAT_WITHDRAW)
    fiat_transfer_list = FiatWithdrawRequest.objects.filter(
        id__gt=tracker.last_id,
        status=DONE
    ).order_by('id')[:threshold]

    for fiat_transfer in fiat_transfer_list:
        event = TransferEvent(
            id=fiat_transfer.id,
            user_id=fiat_transfer.bank_account.user_id,
            amount=fiat_transfer.amount,
            coin='IRT',
            network='IRT',
            created=fiat_transfer.created,
            value_irt=fiat_transfer.amount,
            value_usdt=float(fiat_transfer.amount) / float(usdt_price),
            is_deposit=False,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(fiat_transfer.id) + TransferEvent.type + 'fiat_withdraw'),
            login_activity_id=fiat_transfer.login_activity_id or ''
        )

        get_kafka_producer().produce(event, instance=fiat_transfer)


def trigger_payment_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.PAYMENT)
    payment_list = Payment.objects.filter(
        id__gt=tracker.last_id, status=DONE
    ).order_by('id')[:threshold]
    usdt_price = get_last_price(USDT_IRT)

    for payment in payment_list:
        event = TransferEvent(
            id=payment.id,
            user_id=payment.user_id,
            amount=payment.amount,
            coin='IRT',
            network='IRT',
            is_deposit=True,
            value_usdt=float(payment.amount) / float(usdt_price),
            value_irt=payment.amount,
            created=payment.created,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(payment.id) + TransferEvent.type + 'fiat_deposit')
        )

        get_kafka_producer().produce(event, instance=payment)


def trigger_trade_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.TRADE)
    trade_list = Trade.objects.filter(
        id__gt=tracker.last_id, account__user__isnull=False
    ).exclude(
        account__type=Account.SYSTEM
    ).order_by('id')[:threshold]

    for trade in trade_list:
        if trade.account is None or \
                trade.account.user is None or \
                trade.account.type == Account.SYSTEM or \
                trade.account.user_id in [93167, 382]:
            continue

        event = TradeEvent(
            id=trade.id,
            user_id=trade.account.user_id,
            amount=trade.amount,
            price=trade.price,
            symbol=trade.symbol.name,
            trade_type='market',
            market=trade.market,
            created=trade.created,
            value_usdt=trade.usdt_value,
            value_irt=trade.irt_value,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(trade.id) + TradeEvent.type + 'trade'),
            side=trade.side,
            login_activity_id=trade.login_activity_id or ''
        )

        get_kafka_producer().produce(event, instance=trade)


def trigger_otc_trade(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.OTC_TRADE)
    otc_trade_list = OTCTrade.objects.filter(
        id__gt=tracker.last_id,
        otc_request__account__user__isnull=False,
        status=OTCTrade.DONE
    ).exclude(
        otc_request__account__type=Account.SYSTEM
    ).order_by('id')[:threshold]

    for otc_trade in otc_trade_list:
        trade_type = 'otc'

        req = otc_trade.otc_request
        if FastBuyToken.objects.filter(otc_request=req).exists():
            trade_type = 'fast_buy'

        event = TradeEvent(
            id=otc_trade.id,
            user_id=req.account.user_id,
            amount=req.amount,
            price=req.price,
            symbol=req.symbol.name,
            trade_type=trade_type,
            market=req.market,
            created=otc_trade.created,
            value_usdt=req.usdt_value,
            value_irt=req.irt_value,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(otc_trade.id) + TradeEvent.type + 'otc_trade'),
            side=otc_trade.otc_request.side
        )

        get_kafka_producer().produce(event, instance=otc_trade)


def trigger_login_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.LOGIN)
    login_activity_list = LoginActivity.objects.filter(
        id__gt=tracker.last_id,
    ).order_by('id')[:threshold]

    for login_activity in login_activity_list:
        event = LoginEvent(
            id=login_activity.id,
            user_id=login_activity.user_id,
            device=login_activity.device,
            is_signup=login_activity.is_sign_up,
            created=login_activity.created,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(login_activity.id) + LoginEvent.type),
            user_agent=login_activity.user_agent,
            device_type=login_activity.device_type,
            location=login_activity.location,
            os=login_activity.os,
            browser=login_activity.browser,
            city=login_activity.city,
            country=login_activity.country,
            native_app=login_activity.native_app
        )

        get_kafka_producer().produce(event, instance=login_activity)


def trigger_prize_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.PRIZE)
    prize_list = Prize.objects.filter(
        id__gt=tracker.last_id,
    ).order_by('id')[:threshold]

    for prize in prize_list:
        event = PrizeEvent(
            created=prize.created,
            user_id=prize.account.user_id,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(prize.id) + PrizeEvent.type),
            id=prize.id,
            amount=prize.amount,
            coin=prize.asset.symbol,
            voucher_expiration=prize.voucher_expiration,
            achievement_type=prize.achievement.type,
            value=prize.value
        )
        get_kafka_producer().produce(event, instance=prize)


def trigger_stake_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.STAKING)
    stake_request_list = StakeRequest.objects.filter(
        id__gt=tracker.last_id, status=DONE
    ).order_by('id')[:threshold]

    for stake_request in stake_request_list:
        event = StakeRequestEvent(
            created=stake_request.created,
            user_id=stake_request.account.user_id,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(stake_request.id) + StakeRequestEvent.type),
            stake_request_id=stake_request.id,
            stake_option_id=stake_request.stake_option.id,
            amount=stake_request.amount,
            status=stake_request.status,
            coin=stake_request.stake_option.asset.symbol,
            apr=stake_request.stake_option.apr
        )
        get_kafka_producer().produce(event, instance=stake_request)


def trigger_traffic_source(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.TRAFFIC_SOURCE)
    traffic_source_list = TrafficSource.objects.filter(
        id__gt=tracker.last_id
    ).order_by('id')[:threshold]

    for traffic_source in traffic_source_list:
        event = TrafficSourceEvent(
            created=traffic_source.created,
            user_id=traffic_source.user_id,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(traffic_source.id) + TrafficSourceEvent.type),
            utm_source=traffic_source.utm_source,
            utm_medium=traffic_source.utm_medium,
            utm_campaign=traffic_source.utm_campaign,
            utm_content=traffic_source.utm_content,
            utm_term=traffic_source.utm_term,
        )
        get_kafka_producer().produce(event, instance=traffic_source)


def trigger_wallet_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.WALLET)
    wallet_list = Wallet.objects.filter(
        id__gt=tracker.last_id,
        account__user__isnull=False
    ).order_by('id')[:threshold]

    for wallet in wallet_list:
        event = WalletEvent(
            created=wallet.created,
            user_id=wallet.account.user_id,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(wallet.id) + WalletEvent.type),
            id=wallet.id,
            balance=wallet.balance,
            expiration=wallet.expiration,
            credit=wallet.credit,
            coin=wallet.asset.symbol,
            market=wallet.market
        )
        get_kafka_producer().produce(event, instance=wallet)


def trigger_transaction_event(threshold=1000):
    tracker, _ = EventTracker.objects.get_or_create(type=EventTracker.TRANSACTION)
    trx_list = Trx.objects.filter(
        id__gt=tracker.last_id
    ).order_by('id')[:threshold]

    for trx in trx_list:
        event = TransactionEvent(
            created=trx.created,
            event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(trx.id) + TransactionEvent.type),
            id=trx.id,
            amount=trx.amount,
            sender_wallet_id=trx.sender.id,
            receiver_wallet_id=trx.receiver.id,
            group_id=trx.group_id,
            scope=trx.scope,
            user_id=None
        )
        get_kafka_producer().produce(event, instance=trx)
