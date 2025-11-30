import uuid
from collections import defaultdict

from accounts.models import *
from ledger.models import *
from ledger.utils.external_price import BUY
from ledger.utils.price import get_price

assets = Asset.objects.filter(symbol__in='NWC, DC, RACA, 1M-KISHU, 1M-PIT, 1M-QUACK, 1M-VINU, 1000STARL, 1M-AKITA, SAMO, TON'.replace(' ', '').split(','))

wallets = Wallet.objects.filter(
    asset__in=assets,
    balance__gt=0,
    account__type__isnull=True
)

holders = defaultdict(list)

for w in wallets:
    holders[w.account.user_id].append(w)

group_id = uuid.uuid5(uuid.NAMESPACE_URL, 'delist-NWC-DC-...')

for ws in holders.values():
    user = ws[0].account.user
    coins = ' و '.join(map(lambda w: w.asset.symbol, ws))
    if len(ws) > 1:
        title = 'حذف توکن‌ها'
        msg = 'به منظور حفظ  پایداری و کاهش ریسک، توکن های %s در ۱۵ تیر به طور کامل از صرافی راستین حذف خواهند شد. لطفا تا آن زمان نسبت به فروش یا برداشت این توکن ها اقدام نمایید.' % coins,
    else:
        title = 'حذف توکن'
        msg = 'به منظور حفظ  پایداری و کاهش ریسک، توکن %s در ۱۵ تیر به طور کامل از صرافی راستین حذف خواهد شد. لطفا تا آن زمان نسبت به فروش یا برداشت این توکن اقدام نمایید.' % coins,
    Notification.objects.get_or_create(
        recipient=user,
        group_id=group_id,
        defaults={
            'title': 'حذف توکن‌ها',
            'message': msg,
            'level': Notification.ERROR,
            'link': 'https://raastin.com/ninja/raastin/post/891',
            'push_status': Notification.PUSH_WAITING
        }
    )

# ------------------------------------

for u, ws in holders.items():
    value = 0
    for w in ws:
        price = get_price(
            w.asset.symbol + Asset.USDT,
            side=BUY,
            allow_stale=True,
        )
        value += price * w.balance
    if value > 5:
        coins = ' و '.join(map(lambda w: w.asset.symbol, ws))
        if len(ws) > 1:
            msg = """کاربر گرامی راستین،
به منظور حفظ  پایداری و کاهش ریسک، توکن های %s در ۱۵ تیر به طور کامل از صرافی راستین حذف خواهند شد. لطفا تا آن زمان نسبت به فروش یا برداشت این توکن ها اقدام نمایید.""" % coins
        else:
            msg = """کاربر گرامی راستین،
به منظور حفظ  پایداری و کاهش ریسک، توکن %s در ۱۵ تیر به طور کامل از صرافی راستین حذف خواهد شد. لطفا تا آن زمان نسبت به فروش یا برداشت این توکن اقدام نمایید.""" % coins,
        SmsNotification.objects.get_or_create(
            recipient_id=u,
            group_id=group_id,
            defaults={
                'content': msg,
            }
        )
