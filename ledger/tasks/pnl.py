import logging
from datetime import timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone

from ledger.models import PNLHistory, Wallet, Asset
from ledger.utils.price import get_last_price, USDT_IRT
from ledger.utils.provider import get_provider_requester

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue='history', max_retries=6)
def create_pnl_histories(self):
    try:
        today = timezone.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

        usdt_price = get_provider_requester().get_avg_trade_price(
            symbol='USDTIRT',
            start=today - timedelta(minutes=10),
            end=today
        )

        if not usdt_price:
            usdt_price = get_last_price(USDT_IRT)

        all_in_out = PNLHistory.get_all_in_out(today - timedelta(days=1), today)
        all_wallets = PNLHistory.get_all_wallets()
        last_pnl_histories = PNLHistory.get_last_histories()
        margin_accounts = set(map(lambda k: k[1], filter(lambda w: w[0] == Wallet.MARGIN, all_wallets)))
        excluding_accounts = PNLHistory.get_already_created_pnl_accounts(today)
        pnl_accounts = list(set(map(lambda k: k[1], all_wallets)) - set(excluding_accounts))

        for sliced_pnl_accounts in [pnl_accounts[i:i + 1000] for i in range(0, len(pnl_accounts), 1000)]:
            to_create_pnl_histories = []

            for account in sliced_pnl_accounts:
                for market in (Wallet.SPOT, Wallet.MARGIN):
                    if market == Wallet.MARGIN and account not in margin_accounts:
                        continue
                    last_usdt_snapshot = last_pnl_histories.get((account, market, Asset.USDT), 0)
                    snapshot_balance, profit, input_output_amount = PNLHistory.calculate_amounts_in_usdt(
                        PNLHistory.get_for_account_market(account, market, all_wallets.items()),
                        PNLHistory.get_for_account_market(account, market, all_in_out.items()),
                        last_usdt_snapshot,
                        usdt_price
                    )
                    to_create_pnl_histories.append(
                        PNLHistory(
                            date=today,
                            account_id=account,
                            market=market,
                            base_asset=Asset.USDT,
                            snapshot_balance=snapshot_balance,
                            profit=profit if last_usdt_snapshot else 0,
                        )
                    )

                    irt_snapshot = snapshot_balance * usdt_price
                    last_irt_snapshot = last_pnl_histories.get((account, market, Asset.IRT), 0) + (
                                input_output_amount * usdt_price)

                    to_create_pnl_histories.append(
                        PNLHistory(
                            date=today,
                            account_id=account,
                            market=market,
                            base_asset=Asset.IRT,
                            snapshot_balance=irt_snapshot,
                            profit=irt_snapshot - last_irt_snapshot if last_irt_snapshot else 0,
                        )
                    )

            PNLHistory.objects.bulk_create(to_create_pnl_histories)
    except Exception as e:
        print('PNL error %s' % e)

        try:
            logger.warning(
                'Exception on creating pnl histories', extra={
                    'exp': e,
                    'try': self.request.retries,
                    'date': timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                }
            )
            self.retry(countdown=10 * (2 ** self.request.retries))
        except MaxRetriesExceededError:
            logger.warning(
                'Max retry exceeded on creating pnl histories', extra={
                    'exp': e,
                    'date': timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                }
            )
