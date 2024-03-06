from uuid import UUID

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
