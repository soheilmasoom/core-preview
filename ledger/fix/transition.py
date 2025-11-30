from uuid import uuid4

from accounts.models import Account, Notification
from ledger.models import Asset, Wallet, Trx
from ledger.utils.wallet_pipeline import WalletPipeline

old_asset = Asset.objects.get(symbol='1000FLOKI')
new_asset = Asset.objects.get(symbol='FLOKI')

old_sys_wallet = old_asset.get_wallet(Account.system())
new_sys_wallet = new_asset.get_wallet(Account.system())

old_wallets = Wallet.objects.filter(asset=old_asset, balance__gt=0)

group_id = uuid4()

with WalletPipeline() as pipeline:
    for old_wallet in old_wallets:
        amount = old_wallet.balance
        pipeline.new_trx(
            sender=old_wallet,
            receiver=old_sys_wallet,
            amount=amount,
            group_id=group_id,
            scope=Trx.FIX
        )
        pipeline.new_trx(
            sender=new_sys_wallet,
            receiver=new_asset.get_wallet(old_wallet.account),
            amount=amount * 1000,
            group_id=group_id,
            scope=Trx.FIX
        )
        Notification.send(
            recipient=old_wallet.account.user,
            title='نشان فلوکی تغییر پیدا کرد',
            message='نشان ارز فلوکی از 1000FLOKI به FLOKI تغییر پیدا کرد و مقدار دارایی شما با حفظ ارزش ضرب در ۱۰۰۰ شد.'
        )
