import logging
import uuid
from decimal import Decimal

from celery import shared_task
from django.db.models import F
from django.utils import timezone

from accounts.models import Account, Notification, EmailNotification, SystemConfig
from accounts.tasks import send_message_by_kavenegar
from accounts.utils.admin import url_to_edit_object
from accounts.utils.telegram import send_support_message
from ledger.margin.margin_info import MARGIN_CALL_ML_THRESHOLD, LIQUIDATION_ML_THRESHOLD, \
    MARGIN_CALL_ML_ALERTING_RESOLVE_THRESHOLD, get_bulk_margin_info
from ledger.models import Wallet, MarginPosition, Trx
from ledger.models.position import MarginHistoryModel
from ledger.utils.external_price import SHORT, LONG
from ledger.utils.margin import alert_position_warning
from ledger.utils.wallet_pipeline import WalletPipeline

logger = logging.getLogger(__name__)


@shared_task(queue='margin')
def check_margin_level():
    margin_accounts = set(Wallet.objects.filter(market=Wallet.LOAN, balance__lt=0).values_list('account', flat=True))
    accounts = Account.objects.filter(id__in=margin_accounts, user__isnull=False)

    status = 0

    for account, margin_info in get_bulk_margin_info(accounts).items():
        margin_level = margin_info.get_margin_level()

        logger.info('margin_level for account=%d is %s' % (account.id, margin_level))

        if not account.margin_alerting and margin_level <= MARGIN_CALL_ML_THRESHOLD:
            logger.warning('Send MARGIN_CALL_ML_THRESHOLD for account = %d' % account.id)
            warn_risky_level(account, margin_level)

            if status == 0:
                status = 1

            Account.objects.filter(id=account.id).update(margin_alerting=True)

        elif margin_level > MARGIN_CALL_ML_ALERTING_RESOLVE_THRESHOLD:
            Account.objects.filter(id=account.id).update(margin_alerting=False)

    return status


def warn_risky_level(account: Account, margin_level: Decimal):
    user = account.user

    Notification.send(
        recipient=user,
        title='حساب تعهدی شما در آستانه‌ی تسویه خودکار است.',
        message='لطفا در اسرع وقت نسبت به افزایش دارایی تتری یا کاهش بدهی‌هایتان اقدام کنید. ',
        level=Notification.ERROR
    )

    link = url_to_edit_object(account)
    send_support_message(
        message='Margin account is going to liquidate. (level = %s)' % round(margin_level, 3),
        link=link
    )

    send_message_by_kavenegar(
        phone=user.phone,
        template='alert-margin-liquidation',
        token='تعهدی'
    )


def alert_liquidation(account: Account):
    user = account.user

    Notification.send(
        recipient=user,
        title='حساب تعهدی شما تسویه خودکار شد.',
        message='حساب تعهدی شما به خاطر افزایش بدهی‌هایتان به صورت خودکار تسویه شد.',
        level=Notification.ERROR,
        link='/wallet/margin'
    )

    EmailNotification.send_by_template(
        recipient=user,
        template='margin_liquidated'
    )


@shared_task(queue='margin')
def collect_margin_interest():
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    group_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{now}:{int(now.hour) // 8}")
    interest_history = []
    with WalletPipeline() as pipeline:
        for position in MarginPosition.objects.filter(status=MarginPosition.OPEN).prefetch_related('loan_wallet__asset'):
            if position.debt_amount > Decimal('0'):
                logger.info(f"Collect position:{position.id} Interest fee")
                pipeline.new_trx(
                    position.loan_wallet,
                    position.get_margin_pool_wallet(),
                    abs(position.debt_amount) * position.get_interest_rate(),
                    Trx.MARGIN_INTEREST,
                    group_id,
                )
                interest_history.append(
                    MarginHistoryModel(
                        created=now,
                        position=position,
                        amount=-position.debt_amount * position.get_interest_rate(),
                        group_id=group_id,
                        asset=position.loan_wallet.asset,
                        type=MarginHistoryModel.INTEREST_FEE,
                        account=position.account
                    )
                )
                position.rebalance(pipeline)
                position.set_liquidation_price(pipeline)

        MarginHistoryModel.objects.bulk_create(interest_history)

    to_liquid_short_positions = MarginPosition.objects.filter(
        side=SHORT,
        status=MarginPosition.OPEN,
        liquidation_price__lte=F('symbol__last_trade_price'),
    ).order_by('liquidation_price')

    for position in to_liquid_short_positions:
        position.liquidate(pipeline)

    to_liquid_long_positions = MarginPosition.objects.filter(
        side=LONG,
        status=MarginPosition.OPEN,
        liquidation_price__gte=F('symbol__last_trade_price'),
    ).order_by('liquidation_price')

    for position in to_liquid_long_positions:
        position.liquidate(pipeline)


@shared_task(queue='margin')
def terminate_positions():
    sys = SystemConfig.get_system_config()
    for position in MarginPosition.objects.filter(
            status=MarginPosition.OPEN,
            liquidation_price__isnull=False,
            created__lte=timezone.now() - sys.position_deadline
    ):
        position.close()


@shared_task(queue='margin')
def alert_risky_position():
    queryset = MarginPosition.objects.filter(alert_mode=False, liquidation_price__isnull=False)

    alert_position_warning(queryset.filter(side=SHORT, base_wallet__balance__lte=F('asset_wallet__balance') * F('symbol__last_trade_price') * Decimal('1.15')))
    alert_position_warning(queryset.filter(side=LONG, base_wallet__balance__gte=F('asset_wallet__balance') * F('symbol__last_trade_price') / Decimal('1.15')))

    queryset = MarginPosition.objects.filter(alert_mode=True)

    queryset.filter(side=SHORT,
                    base_wallet__balance__gte=F('asset_wallet__balance') * F('symbol__last_trade_price') * Decimal('1.2'))\
        .update(alert_mode=False)

    queryset.filter(side=LONG,
                    base_wallet__balance__lte=F('asset_wallet__balance') * F('symbol__last_trade_price') / Decimal('1.2'))\
        .update(alert_mode=False)


@shared_task(queue='margin')
def check_position_health():
    for position in (MarginPosition.objects.filter(status=MarginPosition.OPEN)
            .exclude(trade__isnull=True).prefetch_related('asset_wallet', 'base_wallet', 'symbol')):
        margin = position.base_debt_amount + position.base_total_balance
        if margin < 0:
            logger.warning(f"Position{position.id} margin:{margin} is negative !!!")
