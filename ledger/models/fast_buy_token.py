import logging
from decimal import Decimal

from django.db import models
from uuid import uuid4

from accounts.models import Notification
from ledger.models import OTCRequest, Asset, Wallet, OTCTrade
from ledger.utils.fields import DONE
from ledger.utils.fields import get_amount_field
from ledger.utils.precision import humanize_number, humanize_number

logger = logging.getLogger(__name__)


class FastBuyToken(models.Model):
    PROCESS, DEPOSIT, DONE = 'process', 'deposit', 'done'

    CHOICE_STATUS = ((PROCESS, PROCESS), (DEPOSIT, DEPOSIT), (DONE, DONE))

    created = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')

    status = models.CharField(max_length=16, choices=CHOICE_STATUS, default=PROCESS)
    asset = models.ForeignKey('Asset', on_delete=models.CASCADE)
    amount = models.PositiveIntegerField()
    price = get_amount_field()

    payment_request = models.OneToOneField('financial.PaymentRequest', on_delete=models.CASCADE)
    otc_request = models.OneToOneField('OTCRequest', on_delete=models.CASCADE, null=True)

    class Meta:
        verbose_name = verbose_name_plural = 'خرید آنی'

    def __str__(self):
        return '%s IRT (%s)' % (humanize_number(self.amount), self.asset)

    @property
    def user(self):
        return self.payment_request.user

    def create_otc_for_fast_buy_token(self, payment):
        self.status = FastBuyToken.DEPOSIT
        self.save(update_fields=['status'])
        if payment.status == DONE:
            otc_request = OTCRequest.new_trade(
                account=self.user.get_account(),
                from_asset=Asset.get('IRT'),
                to_asset=self.asset,
                from_amount=payment.amount,
                market=Wallet.SPOT,
                order_type=OTCRequest.MARKET
            )
            otc_request.login_activity = self.payment_request.login_activity
            otc_request.save(update_fields=['login_activity'])

            self.otc_request = otc_request
            self.save(update_fields=['otc_request'])

            try:
                otc_trade = OTCTrade.handle_otc_request(otc_request)
                self.status = FastBuyToken.DONE
                self.save(update_fields=['status'])

                Notification.send(
                    recipient=self.user,
                    title='خرید آنی {}'.format(self.asset.name_fa),
                    message='خرید {} {} با موفقیت انجام شد.'.format(humanize_number(otc_request.amount), self.asset.name_fa),
                    level=Notification.SUCCESS
                )
                return otc_trade

            except Exception as exp:
                logger.exception('Error in create otc_trade for fast_buy', extra={
                    'exp': exp
                })
