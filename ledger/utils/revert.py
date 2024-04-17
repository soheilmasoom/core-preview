from uuid import UUID

from django.conf import settings

from accounts.models import Account
from ledger.models import Trx, Wallet
from ledger.utils.wallet_pipeline import WalletPipeline


def revert_trx_group(pipeline: WalletPipeline, group_id: UUID, allow_debt: bool = True):
    for trx in Trx.objects.filter(group_id=group_id):
        if not allow_debt or trx.receiver.has_balance(trx.amount):
            pipeline.new_trx(
                sender=trx.receiver,
                receiver=trx.sender,
                amount=trx.amount,
                group_id=trx.group_id,
                scope=Trx.REVERT
            )
        else:
            pipeline.new_trx(
                sender=trx.receiver.asset.get_wallet(trx.receiver.account, market=Wallet.DEBT),
                receiver=trx.sender,
                amount=trx.amount,
                group_id=trx.group_id,
                scope=Trx.REVERT
            )


def revert_trx_group_via_revert_helper(pipeline: WalletPipeline, account: Account, group_id: UUID):
    trx_list = Trx.objects.filter(group_id=group_id)

    for trx in trx_list.filter(sender=account):
        pipeline.new_trx(
            sender=trx.sender.asset.get_wallet(settings.REVERT_HELPER_ACCOUNT),
            receiver=trx.sender,
            amount=trx.amount,
            group_id=group_id,
            scope=Trx.REVERT
        )

    for trx in trx_list.filter(receiver=account):
        sender = trx.sender

        if not sender.has_balance(trx.amount):
            sender = sender.asset.get_wallet(trx.sender.account, market=Wallet.DEBT)

        pipeline.new_trx(
            sender=sender,
            receiver=trx.sender.asset.get_wallet(settings.REVERT_HELPER_ACCOUNT),
            amount=trx.amount,
            group_id=group_id,
            scope=Trx.REVERT
        )
