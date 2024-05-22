import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Sum
from django.template.loader import render_to_string
from rest_framework.exceptions import ValidationError

from accounts.models import Account, SmsNotification, Notification, EmailNotification
from ledger.models import Wallet
from ledger.utils.external_price import LONG, BUY, SELL, SHORT, USDT, IRT
from market.models import PairSymbol

logger = logging.getLogger(__name__)


def check_margin_view_permission(account: Account, symbol: PairSymbol):
    user = account.user

    if not user.show_margin:
        raise ValidationError('معاملات تعهدی هنوز برای شما فعال نشده است!')

    if not user.margin_quiz_pass_date:
        raise ValidationError('لطفا ابتدا به سوالات آزمون معاملات تعهدی پاسخ دهید.')

    if symbol and not symbol.margin_enable:
        raise ValidationError('شما نمی‌توانید این عملیات را انجام دهید.')


def alert_liquidate(position):
    try:
        message = f'کاربر گرامی موقعیت {position.symbol.name} شما لیکویید شد.'
        tittle = 'لیکویید شدن موقعیت'

        Notification.objects.get_or_create(
            recipient=position.account.user,
            group_id=position.group_id,
            defaults={
                'title': tittle,
                'message': message,
                'hidden': False,
                'push_status': Notification.PUSH_WAITING,
                'source': 'core'
            }
        )

        SmsNotification.objects.get_or_create(
            recipient=position.account.user,
            group_id=position.group_id,
            defaults={
                'content': message,
            }
        )

        EmailNotification.objects.create(
            recipient=position.account.user,
            title=tittle,
            content=message,
            content_html=message
        )

    except Exception as e:
        logger.exception(f'exception on liquid notif ({position.id})', extra={
            'exp': str(e),
        })


def alert_position_warning(positions):
    for position in positions:
        if not position.alert_mode:
            context = {
                'brand': settings.BRAND,
                'symbol': position.symbol.name,
            }

            content = render_to_string('accounts/notif/sms/2fa_forget_success', context=context)

            SmsNotification.objects.get_or_create(
                recipient=position.account.user,
                group_id=position.group_id,
                defaults={
                    'content': content,
                }
            )
    positions.update(alert_mode=True)


def check_margin_order(account, attrs):
    assert attrs['wallet']['market'] == Wallet.MARGIN

    from ledger.models import MarginLeverage, MarginPosition
    from accounts.models import SystemConfig

    if attrs.get('is_open_position') is None:
        raise ValidationError('Cant place margin order without is_open_position')

    if attrs.get('is_open_position') and attrs['side'] == BUY:
        margin_leverage, _ = MarginLeverage.objects.get_or_create(account=account)

        if margin_leverage.leverage == Decimal('1'):
            raise ValidationError('خرید تعهدی با ضریب 1 امکان پذیر نیست.')

    if attrs.get('is_open_position'):
        position_side = SHORT if attrs['side'] == SELL else LONG
    else:
        position_side = SHORT if attrs['side'] == BUY else LONG

    if MarginPosition.objects.filter(
            account=account,
            symbol__name=attrs['symbol']['name'].upper(),
            status=MarginPosition.TERMINATING,
            side=position_side
    ).exists():
        raise ValidationError('Cant place margin order Due to Terminating position')

    if attrs.get('is_open_position'):
        base = USDT if attrs['symbol']['name'].upper().endswith(USDT) else IRT
        sys_config = SystemConfig.get_system_config()
        total_equity = MarginPosition.objects.filter(
            status__in=[MarginPosition.TERMINATING, MarginPosition.OPEN],
            symbol__base_asset__symbol=base
        ).annotate(base_asset_value=F('asset_wallet__balance') * F('symbol__last_trade_price')).\
            aggregate(total_equity=Sum('base_asset_value') + Sum('base_wallet__balance'))['total_equity'] or 0

        if (base == USDT and total_equity >= sys_config.total_margin_usdt_base) or \
                (base == IRT and total_equity >= sys_config.total_margin_irt_base):
            raise ValidationError('در حال حاضر امکان ایجاد موقعیت تعهدی وجود ندارد.')

        user_total_equity = MarginPosition.objects.filter(
            account=account,
            status__in=[MarginPosition.TERMINATING, MarginPosition.OPEN],
            symbol__base_asset__symbol=base
        ).annotate(base_asset_value=F('asset_wallet__balance') * F('symbol__last_trade_price')).\
            aggregate(total_equity=Sum('base_asset_value') + Sum('base_wallet__balance'))['total_equity'] or 0

        leverage = MarginLeverage.objects.get(account=account).leverage
        user_total_equity += Decimal(attrs['price']) * Decimal(attrs['amount']) * (leverage - 1) / leverage

        if (base == USDT and user_total_equity >= sys_config.total_user_margin_usdt_base) or \
                (base == IRT and user_total_equity >= sys_config.total_user_margin_irt_base):
            raise ValidationError('شما به سقف میزان سفارش تعهدی رسیده‌اید.')
