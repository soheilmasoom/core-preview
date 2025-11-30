from django.db.models import Sum, F

from ledger.models import Wallet


def fix_wallets_lock_mismatch(dry_run: bool = True):
    if dry_run:
        print('dry run...')

    non_synced = Wallet.objects.annotate(
        locks=Sum('balancelock__amount')
    ).exclude(locks=F('locked'))

    print('non synced!', list(non_synced.values_list('id', 'locked', 'locks')))

    if not dry_run:
        for wallet in non_synced:
            wallet.locked = wallet.locks
            wallet.save(update_fields=['locked'])

        print('finished syncing')
