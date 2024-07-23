import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from ledger.models.otc_trade import OTCTrade
from ledger.utils.external_price import get_other_side
from ledger.utils.price import get_price


logger = logging.getLogger(__name__)


@shared_task(queue='celery')
def accept_pending_otc_trades():
    expire = timezone.now() - timedelta(seconds=60)

    for otc in OTCTrade.objects.filter(status=OTCTrade.PENDING, execution_type=OTCTrade.PROVIDER, created__lt=expire):
        try:
            otc.hedge_with_provider()
        except Exception as e:
            logger.exception('failed to hedge otc', extra={'exp': e})


@shared_task(queue='celery')
def handle_limit_otc_request():
    try:
        OTCTrade.handle_expired()
        distinct_symbol_and_side = list(OTCTrade.get_untriggered_otc_trade_queryset().distinct("otc_request__symbol", "otc_request__side").values_list("otc_request__symbol__name", "otc_request__side"))
        logger.info('handle limit otc request', extra={'distinct_symbol_and_side': distinct_symbol_and_side})

        for untriggered in distinct_symbol_and_side:
            symbol = untriggered[0]
            side = untriggered[1]

            price = get_price(symbol, side=get_other_side(side))
            OTCTrade.handle_trigger_price(symbol, side, price)
            logger.info('handle limit otc request', extra={'symbol': symbol, 'side': side, 'price': price})

    except Exception as e:
            logger.exception('failed to handle limit otc request', extra={'exp': e})

