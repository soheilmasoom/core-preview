from accounts.models import User, Notification
from accounts.tasks import send_message_by_kavenegar
from ledger.models import Wallet, Trx
from ledger.utils.precision import get_presentation_amount
from ledger.utils.wallet_pipeline import WalletPipeline
from stake.models import StakeRequest


def close_staking(user: User):
    account = user.get_account()

    stake_requests = StakeRequest.objects.filter(
        status=StakeRequest.DONE,
        account=account
    ).select_related('stake_option__asset')

    has_stake_request = stake_requests.exists()

    for stake in stake_requests:
        asset = stake.stake_option.asset
        spot_wallet = asset.get_wallet(account)
        stake_wallet = asset.get_wallet(account=account, market=Wallet.STAKE)

        with WalletPipeline() as pipeline:
            amount = stake.get_locked_amount()

            pipeline.new_trx(
                group_id=stake.group_id,
                sender=stake_wallet,
                receiver=spot_wallet,
                amount=amount,
                scope=Trx.STAKE
            )
            stake.status = StakeRequest.FINISHED
            stake.save()

            Notification.send(
                recipient=user,
                title='لغو استیکینگ',
                message='مقدار %s %s به حساب نقدی‌تان اضافه شد.' % (get_presentation_amount(amount), stake.stake_option.asset.name_fa)
            )

    if has_stake_request:
        send_message_by_kavenegar(
            phone=user.phone,
            template='disable-staking',
            token='استیکینگ'
        )
